"""Seed the database with demo dental office data for a sample tenant."""

import asyncio

from sqlalchemy import select

from app.auth import hash_password
from app.database import async_session
from app.models import AvailabilityRule, OfficeConfig, Patient, Provider, Tenant, User

DEMO_TENANT_ID = "00000000-0000-0000-0000-000000000001"


async def seed():
    async with async_session() as db:
        # Create or verify tenant
        result = await db.execute(select(Tenant).where(Tenant.id == DEMO_TENANT_ID))
        tenant = result.scalar_one_or_none()
        if not tenant:
            tenant = Tenant(
                id=DEMO_TENANT_ID,
                name="Bright Smile Dental",
                slug="bright-smile-dental",
                twilio_phone_number="+15064092543",
                emergency_phone="+14155550911",
                transfer_phone="+14155550100",
                greeting_message="Hi, thank you for calling Bright Smile Dental! How can I help you today?",
                timezone="America/Los_Angeles",
            )
            db.add(tenant)
            await db.flush()
        else:
            # Update existing default tenant with full details
            tenant.name = "Bright Smile Dental"
            tenant.slug = "bright-smile-dental"
            tenant.twilio_phone_number = tenant.twilio_phone_number or "+14155550100"
            tenant.emergency_phone = tenant.emergency_phone or "+14155550911"
            tenant.transfer_phone = tenant.transfer_phone or "+14155550100"
            tenant.greeting_message = tenant.greeting_message or "Hi, thank you for calling Bright Smile Dental! How can I help you today?"
            await db.flush()

        # Create super admin user if none exists
        admin_result = await db.execute(select(User).where(User.role == "super_admin").limit(1))
        if not admin_result.scalar_one_or_none():
            admin_user = User(
                tenant_id=DEMO_TENANT_ID,
                email="admin@example.com",
                hashed_password=hash_password("admin123"),
                role="super_admin",
            )
            db.add(admin_user)

        # Check if providers already exist for this tenant
        prov_result = await db.execute(
            select(Provider).where(Provider.tenant_id == DEMO_TENANT_ID).limit(1)
        )
        if prov_result.scalars().first():
            await db.commit()
            print("Database already seeded — skipping data creation.")
            return

        dr_smith = Provider(
            id="prov-001",
            tenant_id=DEMO_TENANT_ID,
            name="Dr. Sarah Smith",
            title="DDS",
            specialties="General Dentistry, Cosmetic Dentistry, Crowns",
        )
        dr_patel = Provider(
            id="prov-002",
            tenant_id=DEMO_TENANT_ID,
            name="Dr. Raj Patel",
            title="DMD",
            specialties="Orthodontics, Pediatric Dentistry, Extractions",
        )
        db.add_all([dr_smith, dr_patel])

        for day in range(5):
            db.add(AvailabilityRule(tenant_id=DEMO_TENANT_ID, provider_id="prov-001", day_of_week=day, start_time="09:00", end_time="17:00"))
            db.add(AvailabilityRule(tenant_id=DEMO_TENANT_ID, provider_id="prov-002", day_of_week=day, start_time="08:00", end_time="16:00"))

        db.add(AvailabilityRule(tenant_id=DEMO_TENANT_ID, provider_id="prov-001", day_of_week=5, start_time="09:00", end_time="13:00"))

        db.add_all([
            Patient(
                id="pat-001", tenant_id=DEMO_TENANT_ID, first_name="John", last_name="Doe",
                phone="+15551234567", email="john.doe@email.com",
                date_of_birth="1985-06-15", insurance_provider="Delta Dental",
            ),
            Patient(
                id="pat-002", tenant_id=DEMO_TENANT_ID, first_name="Jane", last_name="Garcia",
                phone="+15559876543", email="jane.garcia@email.com",
                date_of_birth="1990-03-22", insurance_provider="Cigna Dental",
            ),
        ])

        config_entries = [
            ("office_name", "Bright Smile Dental", "general"),
            ("office_address", "123 Main Street, Suite 200, San Francisco, CA 94102", "general"),
            ("office_phone", "+14155550100", "general"),
            ("office_hours", "Monday-Friday 8:00 AM - 5:00 PM, Saturday 9:00 AM - 1:00 PM, Sunday Closed", "general"),
            ("emergency_phone", "+14155550911", "general"),
            ("insurance_accepted", "Delta Dental, Cigna, Aetna, MetLife, Guardian, United Healthcare Dental, BlueCross BlueShield", "insurance"),
            ("payment_methods", "Cash, Credit/Debit Cards, HSA/FSA, CareCredit financing available", "billing"),
            ("cancellation_policy", "Please provide at least 24 hours notice for cancellations. Late cancellations may incur a $50 fee.", "policy"),
            ("new_patient_info", "New patients should arrive 15 minutes early to complete paperwork. Please bring your insurance card, photo ID, and a list of current medications.", "policy"),
            ("faq_whitening", "We offer both in-office and take-home whitening options. In-office whitening takes about 60 minutes and costs $350. Take-home kits are $200.", "faq"),
            ("faq_emergency", "For dental emergencies outside office hours, call our emergency line at +14155550911. If you are experiencing severe bleeding or trauma, please go to the nearest emergency room.", "faq"),
            ("faq_xrays", "We recommend dental X-rays once a year for most patients. Digital X-rays are included as part of your exam visit.", "faq"),
            ("faq_first_visit", "Your first visit will include a comprehensive exam, X-rays, and a cleaning. It typically takes about 90 minutes.", "faq"),
            ("faq_insurance_billing", "We accept most major dental insurance plans. We will file claims on your behalf. Your estimated copay will be collected at the time of service.", "faq"),
            ("faq_parking", "Free parking is available in the building garage. Enter from Oak Street and take a ticket — we validate.", "faq"),
        ]
        for key, value, category in config_entries:
            db.add(OfficeConfig(tenant_id=DEMO_TENANT_ID, key=key, value=value, category=category))

        await db.commit()
        print("Database seeded successfully with demo tenant 'Bright Smile Dental'.")


if __name__ == "__main__":
    asyncio.run(seed())
