"""Seed the database with demo dental office data."""

import asyncio

from sqlalchemy import select

from app.database import async_session, init_db
from app.models import AvailabilityRule, OfficeConfig, Patient, Provider


async def seed():
    await init_db()

    async with async_session() as db:
        result = await db.execute(select(Provider).limit(1))
        if result.scalars().first():
            print("Database already seeded — skipping.")
            return

        dr_smith = Provider(
            id="prov-001",
            name="Dr. Sarah Smith",
            title="DDS",
            specialties="General Dentistry, Cosmetic Dentistry, Crowns",
        )
        dr_patel = Provider(
            id="prov-002",
            name="Dr. Raj Patel",
            title="DMD",
            specialties="Orthodontics, Pediatric Dentistry, Extractions",
        )
        db.add_all([dr_smith, dr_patel])

        for day in range(5):
            db.add(AvailabilityRule(provider_id="prov-001", day_of_week=day, start_time="09:00", end_time="17:00"))
            db.add(AvailabilityRule(provider_id="prov-002", day_of_week=day, start_time="08:00", end_time="16:00"))

        db.add(AvailabilityRule(provider_id="prov-001", day_of_week=5, start_time="09:00", end_time="13:00"))

        db.add_all([
            Patient(
                id="pat-001", first_name="John", last_name="Doe",
                phone="+15551234567", email="john.doe@email.com",
                date_of_birth="1985-06-15", insurance_provider="Delta Dental",
            ),
            Patient(
                id="pat-002", first_name="Jane", last_name="Garcia",
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
            db.add(OfficeConfig(key=key, value=value, category=category))

        await db.commit()
        print("Database seeded successfully.")


if __name__ == "__main__":
    asyncio.run(seed())
