"""Seed the database with a demo organization and sample data.

Run:  python -m app.seed

This creates demo accounts with weak, well-known passwords and is intended for
local development only. It refuses to run when ACP_ENVIRONMENT=production.
"""
from datetime import time

from app.core.config import Settings, get_settings
from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models import (
    AccessLevel,
    AccessLevelDoor,
    Cardholder,
    Controller,
    Credential,
    Department,
    Door,
    Organization,
    Schedule,
    ScheduleInterval,
    Shift,
    Site,
    User,
    UserRole,
)


def seed(cfg: Settings | None = None) -> None:
    cfg = cfg or get_settings()
    if cfg.is_production:
        raise SystemExit(
            "Refusing to run the demo seed in production. It creates accounts with "
            "well-known passwords; provision real accounts instead."
        )
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            print("Database already has users; skipping seed.")
            return

        demo = Organization(name="Demo Company", slug="demo", contact_email="demo@example.com", plan="pro")
        db.add(demo)
        db.flush()

        superadmin = User(
            email=cfg.first_superuser_email.lower(),
            full_name="Platform Admin",
            hashed_password=hash_password(cfg.first_superuser_password),
            role=UserRole.SUPER_ADMIN,
            organization_id=demo.id,
        )
        org_admin = User(
            email="demo-admin@example.com",
            full_name="Demo Admin",
            hashed_password=hash_password("demo1234"),
            role=UserRole.ADMIN,
            organization_id=demo.id,
        )
        operator = User(
            email="demo-operator@example.com",
            full_name="Demo Operator",
            hashed_password=hash_password("demo1234"),
            role=UserRole.OPERATOR,
            organization_id=demo.id,
        )
        db.add_all([superadmin, org_admin, operator])

        site = Site(organization_id=demo.id, name="Head Office", address="123 Main St", timezone="UTC")
        db.add(site)
        db.flush()

        controller = Controller(
            organization_id=demo.id,
            site_id=site.id,
            name="Main Entrance Board",
            serial_number="223000001",
            ip_address="192.168.1.100",
        )
        db.add(controller)
        db.flush()
        doors = [
            Door(organization_id=demo.id, controller_id=controller.id, number=n, name=name)
            for n, name in enumerate(["Front Door", "Back Door", "Warehouse", "Server Room"], start=1)
        ]
        db.add_all(doors)
        db.flush()

        office_hours = Schedule(
            organization_id=demo.id,
            name="Office Hours",
            description="Mon-Fri 08:00-18:00",
            intervals=[
                ScheduleInterval(day_of_week=d, start_time=time(8, 0), end_time=time(18, 0))
                for d in range(5)
            ],
        )
        db.add(office_hours)
        db.flush()

        full_access = AccessLevel(
            organization_id=demo.id,
            name="Full Access 24/7",
            description="All doors, no schedule restriction",
            door_rules=[AccessLevelDoor(door_id=d.id) for d in doors],
        )
        staff_access = AccessLevel(
            organization_id=demo.id,
            name="Staff (Office Hours)",
            description="Front and back door during office hours",
            door_rules=[
                AccessLevelDoor(door_id=doors[0].id, schedule_id=office_hours.id),
                AccessLevelDoor(door_id=doors[1].id, schedule_id=office_hours.id),
            ],
        )
        db.add_all([full_access, staff_access])
        db.flush()

        it_dept = Department(organization_id=demo.id, name="IT")
        sales_dept = Department(organization_id=demo.id, name="Sales")
        db.add_all([it_dept, sales_dept])
        db.flush()

        day_shift = Shift(
            organization_id=demo.id,
            name="Turno diurno",
            start_time=time(9, 0),
            end_time=time(18, 0),
            days_of_week=[0, 1, 2, 3, 4],
        )
        db.add(day_shift)
        db.flush()

        alice = Cardholder(
            organization_id=demo.id, department_id=it_dept.id, shift_id=day_shift.id,
            first_name="Alice", last_name="Garcia", employee_number="E-001",
            email="alice@example.com",
        )
        bob = Cardholder(
            organization_id=demo.id, department_id=sales_dept.id, shift_id=day_shift.id,
            first_name="Bob", last_name="Lopez", employee_number="E-002",
            email="bob@example.com",
        )
        alice.access_levels = [full_access]
        bob.access_levels = [staff_access]
        db.add_all([alice, bob])
        db.flush()
        db.add_all(
            [
                Credential(organization_id=demo.id, cardholder_id=alice.id, card_number="10001"),
                Credential(organization_id=demo.id, cardholder_id=bob.id, card_number="10002"),
            ]
        )

        db.commit()
        print("Seed complete. Demo accounts created (development only):")
        print(f"  Super admin: {cfg.first_superuser_email}")
        print("  Org admin:   demo-admin@example.com")
        print("  Operator:    demo-operator@example.com")
        print("Passwords are the configured/demo development defaults; change them before any real use.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
