import secrets
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from core.models import User, OrgUnit, MedicalRecord, OfferWorkflow
from core.models_offers import Offer, OfferTemplate, OfferSendToken


class Command(BaseCommand):
    help = "Seed rich test data (Departments, HRBPs, Locations, Medical Approvers, Employees & Offers)"

    def handle(self, *args, **options):
        self.stdout.write("Seeding portal test data...")
        password = "qwerty1234"

        with transaction.atomic():
            # Clear old duplicate departments and locations to prevent seeding errors
            OrgUnit.objects.all().delete()

            # 1. DEPARTMENTS
            dept_data = [
                ("Engineering", "ENG", 1),
                ("Human Resources", "HR", 2),
                ("Finance & Accounting", "FIN", 3),
                ("Sales & Marketing", "MKT", 4),
                ("Operations & Logistics", "OPS", 5),
            ]
            depts = {}
            for name, code, order in dept_data:
                dept, _ = OrgUnit.objects.update_or_create(
                    kind="department",
                    name=name,
                    defaults={"code": code, "display_order": order, "is_active": True}
                )
                depts[code] = dept
            self.stdout.write(f"  Created/Updated {len(depts)} Departments")

            # 2. LOCATIONS
            loc_data = [
                ("New York HQ", "NYC", 1),
                ("London Regional Office", "LDN", 2),
                ("Singapore Tech Hub", "SGP", 3),
            ]
            locs = {}
            for name, code, order in loc_data:
                loc, _ = OrgUnit.objects.update_or_create(
                    kind="location",
                    name=name,
                    defaults={"code": code, "display_order": order, "is_active": True}
                )
                locs[name] = loc
            self.stdout.write(f"  Created/Updated {len(locs)} Locations")

            # 3. HRBPS (HR Business Partners)
            hrbp_data = [
                ("Sarah Smith", "hrbp.smith@company.com", [depts["ENG"].id, depts["FIN"].id]),
                ("David Jones", "hrbp.jones@company.com", [depts["MKT"].id, depts["OPS"].id]),
                ("Emma Williams", "hrbp.williams@company.com", [depts["HR"].id]),
            ]
            hrbps = []
            for full_name, email, dept_ids in hrbp_data:
                hrbp, created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        "full_name": full_name,
                        "role": "hrbp",
                        "department": depts["HR"],
                        "scope": {"departments": dept_ids},
                        "is_active": True,
                    }
                )
                hrbp.set_password(password)
                hrbp.scope = {"departments": dept_ids}
                hrbp.role = "hrbp"
                hrbp.save()
                hrbps.append(hrbp)
            self.stdout.write(f"  Created/Updated {len(hrbps)} HRBPs with department scopes")

            # 4. MEDICAL APPROVERS
            med_data = [
                ("Dr. Robert Carter", "dr.carter@company.com", ["New York HQ", "London Regional Office"]),
                ("Dr. Ananya Patel", "dr.patel@company.com", ["Singapore Tech Hub"]),
            ]
            med_approvers = []
            for full_name, email, locations in med_data:
                doc, created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        "full_name": full_name,
                        "role": "medical_approver",
                        "department": depts["HR"],
                        "scope": {"locations": locations},
                        "is_active": True,
                    }
                )
                doc.set_password(password)
                doc.scope = {"locations": locations}
                doc.role = "medical_approver"
                doc.save()
                med_approvers.append(doc)
            self.stdout.write(f"  Created/Updated {len(med_approvers)} Medical Approvers with location scopes")

            # 5. DEFAULT OFFER TEMPLATE
            offer_template, _ = OfferTemplate.objects.get_or_create(
                name="Standard Employment Offer",
                defaults={
                    "description": "Standard full-time employment agreement template",
                    "html_content": "<h2>Employment Offer</h2><p>Welcome to OnboardHub!</p>",
                    "is_default": True,
                }
            )

            # 5.5. MEDICAL CATALOG REQUIREMENT
            MedicalRecord.objects.get_or_create(
                requirement_name="Pre-Employment Health Screening",
                is_catalog=True,
                defaults={
                    "is_required": True,
                    "description": "Please upload your pre-employment health screening report.",
                    "is_active": True,
                }
            )

            # 6. EMPLOYEES & OFFERS (All starting at beginning)
            employee_specs = [
                ("Alex Rivera", "alex.rivera@test.com", "EMP-1001", depts["ENG"], "New York HQ", "Software Engineer", 105000),
                ("Maya Lin", "maya.lin@test.com", "EMP-1002", depts["ENG"], "Singapore Tech Hub", "Product Designer", 95000),
                ("Liam Davies", "liam.davies@test.com", "EMP-1003", depts["FIN"], "London Regional Office", "Financial Analyst", 88000),
                ("Sophia Zhang", "sophia.zhang@test.com", "EMP-1004", depts["HR"], "New York HQ", "HR Specialist", 82000),
                ("Ethan Hunt", "ethan.hunt@test.com", "EMP-1005", depts["MKT"], "London Regional Office", "Account Executive", 90000),
                ("Nadia Ali", "nadia.ali@test.com", "EMP-1006", depts["OPS"], "Singapore Tech Hub", "Operations Coordinator", 78000),
            ]

            # Clear old test data for these candidate emails to ensure a clean re-seed
            emails = [spec[1] for spec in employee_specs]
            Offer.objects.filter(candidate_email__in=emails).delete()
            OfferWorkflow.objects.filter(employee__email__in=emails).delete()
            MedicalRecord.objects.filter(employee__email__in=emails, is_catalog=False).delete()

            created_employees = []
            offer_details = []

            admin_user = User.objects.filter(role="super_admin").first() or User.objects.filter(role="admin").first()

            for full_name, email, emp_id, dept, loc_name, title, comp in employee_specs:
                emp, _ = User.objects.get_or_create(
                    email=email,
                    defaults={
                        "employee_id": emp_id,
                        "full_name": full_name,
                        "role": "employee",
                        "department": dept,
                        "location_code": loc_name,
                        "position_title": title,
                        "status": "pending",
                        "date_of_joining": timezone.now().date() + timezone.timedelta(days=14),
                        "is_active": True,
                    }
                )
                emp.set_password(password)
                emp.status = "pending"
                emp.department = dept
                emp.location_code = loc_name
                emp.position_title = title
                emp.save()
                created_employees.append(emp)

                # Create Offer (Status: Sent)
                offer, offer_created = Offer.objects.get_or_create(
                    candidate_email=email,
                    defaults={
                        "candidate_name": full_name,
                        "candidate_user": emp,
                        "template": offer_template,
                        "status": "sent",
                        "total_compensation": comp,
                        "sent_at": timezone.now(),
                        "created_by": admin_user,
                        "rendered_html": f"""
                        <div style="font-family: Arial, sans-serif; padding: 20px; line-height: 1.6;">
                            <h2 style="color: #2563eb;">OFFER OF EMPLOYMENT</h2>
                            <p>Dear <strong>{full_name}</strong>,</p>
                            <p>We are delighted to offer you the position of <strong>{title}</strong> at OnboardHub!</p>
                            <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                                <tr><td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Department:</strong></td><td style="padding: 8px; border-bottom: 1px solid #ddd;">{dept.name}</td></tr>
                                <tr><td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Work Location:</strong></td><td style="padding: 8px; border-bottom: 1px solid #ddd;">{loc_name}</td></tr>
                                <tr><td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Annual Salary:</strong></td><td style="padding: 8px; border-bottom: 1px solid #ddd;">${comp:,.2f} USD</td></tr>
                                <tr><td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Start Date:</strong></td><td style="padding: 8px; border-bottom: 1px solid #ddd;">{(timezone.now() + timezone.timedelta(days=14)).strftime('%B %d, %Y')}</td></tr>
                            </table>
                            <p>Please review and sign this offer letter electronically to accept your offer and begin your onboarding journey.</p>
                        </div>
                        """
                    }
                )

                # Tokens for viewing/signing offer
                view_tok, _ = OfferSendToken.objects.get_or_create(offer=offer, token_type="view", defaults={"token": secrets.token_urlsafe(32)})
                accept_tok, _ = OfferSendToken.objects.get_or_create(offer=offer, token_type="accept", defaults={"token": secrets.token_urlsafe(32)})
                reject_tok, _ = OfferSendToken.objects.get_or_create(offer=offer, token_type="reject", defaults={"token": secrets.token_urlsafe(32)})

                offer_details.append({
                    "name": full_name,
                    "email": email,
                    "dept": dept.name,
                    "location": loc_name,
                    "offer_id": offer.id,
                    "view_url": f"/public/offers/{view_tok.token}/",
                })

            self.stdout.write(f"  Created/Updated {len(created_employees)} Employees with Sent Offers & Medical Records")

        self.stdout.write(self.style.SUCCESS("[OK] Test data successfully seeded!"))
        self.stdout.write("\n=== TEST CREDENTIALS (Password for all: qwerty1234) ===")
        self.stdout.write("\n--- HRBPs ---")
        for hrbp in hrbps:
            self.stdout.write(f"  • {hrbp.full_name} ({hrbp.email}) -> Scopes: {hrbp.scope}")
        self.stdout.write("\n--- MEDICAL APPROVERS ---")
        for doc in med_approvers:
            self.stdout.write(f"  • {doc.full_name} ({doc.email}) -> Scopes: {doc.scope}")
        self.stdout.write("\n--- NEW CANDIDATES / EMPLOYEES (Offers Sent) ---")
        for info in offer_details:
            self.stdout.write(f"  • {info['name']} ({info['email']}) | {info['dept']} ({info['location']})")
            self.stdout.write(f"    Public Offer Sign Link: http://127.0.0.1:8000{info['view_url']}")
