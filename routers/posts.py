from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
import schemmas
from auth import get_current_user
from database import get_db

router = APIRouter(prefix="/posts", tags=["posts"])

ALLOWED_TOPICS = {"natureza", "agricultura", "turismo"}


def _ensure_admin(current_user: models.User) -> None:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Apenas admin pode publicar")


def _count_post_likes(db: Session, post_id: int) -> int:
    return (
        db.query(func.count(models.PostLike.id))
        .filter(models.PostLike.post_id == post_id)
        .scalar()
        or 0
    )


def _build_post_out(post: models.Post, current_user_id: int, db: Session) -> schemmas.PostOut:
    likes_count = _count_post_likes(db, post.id)
    comments_count = (
        db.query(func.count(models.PostComment.id))
        .filter(models.PostComment.post_id == post.id)
        .scalar()
        or 0
    )
    liked_by_me = (
        db.query(models.PostLike.id)
        .filter(
            models.PostLike.post_id == post.id,
            models.PostLike.user_id == current_user_id,
        )
        .first()
        is not None
    )

    return schemmas.PostOut(
        id=post.id,
        title=post.title,
        content=post.content,
        topic=post.topic,
        image_url=post.image_url,
        created_at=post.created_at,
        updated_at=post.updated_at,
        likes_count=likes_count,
        comments_count=comments_count,
        liked_by_me=liked_by_me,
        author=schemmas.PostAuthor(
            id=post.author.id,
            name=post.author.name,
            username=post.author.username,
            avatar=post.author.avatar,
        ),
    )


@router.get("/", response_model=list[schemmas.PostOut])
def list_posts(
    topic: schemmas.TopicLiteral | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.Post).order_by(models.Post.created_at.desc())
    if topic:
        query = query.filter(models.Post.topic == topic)
    posts = query.offset(offset).limit(limit).all()
    return [_build_post_out(post, current_user.id, db) for post in posts]


@router.get("/{post_id}", response_model=schemmas.PostOut)
def get_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post nao encontrado")
    return _build_post_out(post, current_user.id, db)


@router.post("/", response_model=schemmas.PostOut, status_code=status.HTTP_201_CREATED)
def create_post(
    payload: schemmas.PostCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _ensure_admin(current_user)

    if payload.topic not in ALLOWED_TOPICS:
        raise HTTPException(status_code=400, detail="Tema invalido")

    post = models.Post(
        title=payload.title.strip(),
        content=payload.content.strip(),
        topic=payload.topic,
        image_url=payload.image_url,
        author_id=current_user.id,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return _build_post_out(post, current_user.id, db)


@router.put("/{post_id}", response_model=schemmas.PostOut)
def update_post(
    post_id: int,
    payload: schemmas.PostUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _ensure_admin(current_user)
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post nao encontrado")

    if payload.title is not None:
        post.title = payload.title.strip()
    if payload.content is not None:
        post.content = payload.content.strip()
    if payload.topic is not None:
        if payload.topic not in ALLOWED_TOPICS:
            raise HTTPException(status_code=400, detail="Tema invalido")
        post.topic = payload.topic
    if payload.image_url is not None:
        post.image_url = payload.image_url

    db.commit()
    db.refresh(post)
    return _build_post_out(post, current_user.id, db)


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _ensure_admin(current_user)
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post nao encontrado")
    db.delete(post)
    db.commit()
    return None


@router.post("/{post_id}/like", response_model=schemmas.PostLikeToggleOut)
def toggle_like(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post nao encontrado")

    like = (
        db.query(models.PostLike)
        .filter(
            models.PostLike.post_id == post_id,
            models.PostLike.user_id == current_user.id,
        )
        .first()
    )

    if like:
        db.delete(like)
        liked = False
    else:
        db.add(models.PostLike(post_id=post_id, user_id=current_user.id))
        try:
            db.commit()
            liked = True
        except IntegrityError:
            db.rollback()
            liked = (
                db.query(models.PostLike.id)
                .filter(
                    models.PostLike.post_id == post_id,
                    models.PostLike.user_id == current_user.id,
                )
                .first()
                is not None
            )
            return schemmas.PostLikeToggleOut(
                liked=liked,
                likes_count=_count_post_likes(db, post_id),
            )

    if like:
        db.commit()

    likes_count = _count_post_likes(db, post_id)
    return schemmas.PostLikeToggleOut(liked=liked, likes_count=likes_count)


@router.get("/{post_id}/comments", response_model=list[schemmas.PostCommentOut])
def list_comments(
    post_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _ = current_user
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post nao encontrado")

    comments = (
        db.query(models.PostComment)
        .filter(models.PostComment.post_id == post_id)
        .order_by(models.PostComment.created_at.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        schemmas.PostCommentOut(
            id=comment.id,
            post_id=comment.post_id,
            content=comment.content,
            created_at=comment.created_at,
            updated_at=comment.updated_at,
            user=schemmas.PostAuthor(
                id=comment.user.id,
                name=comment.user.name,
                username=comment.user.username,
                avatar=comment.user.avatar,
            ),
        )
        for comment in comments
    ]


@router.post(
    "/{post_id}/comments",
    response_model=schemmas.PostCommentOut,
    status_code=status.HTTP_201_CREATED,
)
def create_comment(
    post_id: int,
    payload: schemmas.PostCommentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post nao encontrado")

    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Comentario vazio")

    comment = models.PostComment(
        post_id=post_id,
        user_id=current_user.id,
        content=content,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return schemmas.PostCommentOut(
        id=comment.id,
        post_id=comment.post_id,
        content=comment.content,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        user=schemmas.PostAuthor(
            id=current_user.id,
            name=current_user.name,
            username=current_user.username,
            avatar=current_user.avatar,
        ),
    )


@router.delete("/{post_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    post_id: int,
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    comment = (
        db.query(models.PostComment)
        .filter(
            models.PostComment.id == comment_id,
            models.PostComment.post_id == post_id,
        )
        .first()
    )
    if not comment:
        raise HTTPException(status_code=404, detail="Comentario nao encontrado")
    if not current_user.is_admin and comment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Sem permissao para remover comentario")
    db.delete(comment)
    db.commit()
    return None
