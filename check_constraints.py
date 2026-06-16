from database import SessionLocal, engine
from sqlalchemy import inspect

inspector = inspect(engine)

print("=== Lodging Rooms Constraints ===")
for constraint in inspector.get_unique_constraints("lodging_rooms"):
    print(f"Name: {constraint['name']}, Columns: {constraint['column_names']}")

print("\n=== Conference Rooms Constraints ===")
for constraint in inspector.get_unique_constraints("conference_rooms"):
    print(f"Name: {constraint['name']}, Columns: {constraint['column_names']}")