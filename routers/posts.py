from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File, Form
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
import schemmas
from auth import get_current_user
from database import get_db
from controllers.storage_manager import POSTS_FOLDER, storage_manager

router = APIRouter(prefix="/posts", tags=["posts"])

ALLOWED_TOPICS = {"natureza", "agricultura", "turismo"}
ALLOWED_STATUSES = {"draft", "published"}


def _ensure_admin(current_user: models.User) -> None:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Apenas admin pode publicar")


def _can_access_post(post: models.Post, current_user: models.User) -> bool:
    return post.status == "published" or current_user.is_admin or post.author_id == current_user.id


def _ensure_post_visible(post: models.Post, current_user: models.User) -> None:
    if not _can_access_post(post, current_user):
        raise HTTPException(status_code=404, detail="Post nao encontrado")


def _resolve_post_status(
    requested_status: schemmas.PostStatusLiteral | None,
    current_user: models.User,
) -> str:
    resolved_status = requested_status or "draft"
    if resolved_status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="Estado invalido")
    if resolved_status == "published" and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Apenas admin pode publicar")
    return resolved_status


def _count_post_likes(db: Session, post_id: int) -> int:
    return (
        db.query(func.count(models.PostLike.id))
        .filter(models.PostLike.post_id == post_id)
        .scalar()
        or 0
    )


async def _resolve_post_image_url(
    image: UploadFile | None,
) -> str | None:
    if image is not None:
        return await storage_manager.upload_file(
            image,
            POSTS_FOLDER,
            allowed_mime_prefixes=("image/",),
        )
    return None


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
        category=post.topic,
        status=post.status,
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
    query = (
        db.query(models.Post)
        .filter(models.Post.status == "published")
        .order_by(models.Post.created_at.desc())
    )
    if topic:
        query = query.filter(models.Post.topic == topic)
    posts = query.offset(offset).limit(limit).all()
    return [_build_post_out(post, current_user.id, db) for post in posts]


@router.get("/me", response_model=list[schemmas.PostOut])
def list_my_posts(
    status: schemmas.PostStatusLiteral | None = Query(default=None),
    topic: schemmas.TopicLiteral | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = (
        db.query(models.Post)
        .filter(models.Post.author_id == current_user.id)
        .order_by(models.Post.created_at.desc())
    )
    if status:
        query = query.filter(models.Post.status == status)
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
    _ensure_post_visible(post, current_user)
    return _build_post_out(post, current_user.id, db)


@router.post("/", response_model=schemmas.PostOut, status_code=status.HTTP_201_CREATED)
async def create_post(
    title: str = Form(...),
    content: str = Form(...),
    category: schemmas.TopicLiteral | None = Form(default=None),
    topic: schemmas.TopicLiteral | None = Form(default=None),
    status: schemmas.PostStatusLiteral = Form(default="draft"),
    image: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    resolved_category = category or topic
    if not resolved_category:
        raise HTTPException(status_code=400, detail="Categoria e obrigatoria")

    if resolved_category not in ALLOWED_TOPICS:
        raise HTTPException(status_code=400, detail="Tema invalido")

    clean_title = title.strip()
    clean_content = content.strip()
    if len(clean_title) < 3:
        raise HTTPException(status_code=400, detail="Titulo invalido")
    if len(clean_content) < 3:
        raise HTTPException(status_code=400, detail="Conteudo invalido")

    resolved_status = _resolve_post_status(status, current_user)
    resolved_image_url = await _resolve_post_image_url(image)

    post = models.Post(
        title=clean_title,
        content=clean_content,
        topic=resolved_category,
        status=resolved_status,
        image_url=resolved_image_url,
        author_id=current_user.id,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return _build_post_out(post, current_user.id, db)


@router.put("/{post_id}", response_model=schemmas.PostOut)
async def update_post(
    post_id: int,
    title: str | None = Form(default=None),
    content: str | None = Form(default=None),
    category: schemmas.TopicLiteral | None = Form(default=None),
    topic: schemmas.TopicLiteral | None = Form(default=None),
    status: schemmas.PostStatusLiteral | None = Form(default=None),
    image: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post nao encontrado")
    if not current_user.is_admin and post.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Sem permissao para editar post")

    if title is not None:
        clean_title = title.strip()
        if len(clean_title) < 3:
            raise HTTPException(status_code=400, detail="Titulo invalido")
        post.title = clean_title
    if content is not None:
        clean_content = content.strip()
        if len(clean_content) < 3:
            raise HTTPException(status_code=400, detail="Conteudo invalido")
        post.content = clean_content
    next_category = category if category is not None else topic
    if next_category is not None:
        if next_category not in ALLOWED_TOPICS:
            raise HTTPException(status_code=400, detail="Tema invalido")
        post.topic = next_category
    if status is not None:
        post.status = _resolve_post_status(status, current_user)
    if image is not None:
        post.image_url = await _resolve_post_image_url(image)

    db.commit()
    db.refresh(post)
    return _build_post_out(post, current_user.id, db)


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post nao encontrado")
    if not current_user.is_admin and post.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Sem permissao para remover post")
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
    if post.status != "published":
        raise HTTPException(status_code=403, detail="Nao e possivel curtir rascunho")

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
    if post.status != "published":
        raise HTTPException(status_code=403, detail="Comentarios disponiveis apenas em posts publicados")

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
    if post.status != "published":
        raise HTTPException(status_code=403, detail="Nao e possivel comentar em rascunho")

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
