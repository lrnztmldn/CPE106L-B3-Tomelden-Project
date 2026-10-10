"""
===============================================================================
 IronCore Fitness - Gym Membership and Attendance Management System
 Python / Tkinter version  |  CPE106L-4 / B3  |  Lorenz Daniel G. Tomelden
===============================================================================
 HOW TO RUN (Windows):  double-click this file, or open a terminal and type
                        python gym_system.py
 Needs only the standard Python install (3.8 or newer). No pip packages.

 DEFAULT LOGINS:   admin / admin123   (Admin / Owner)
                   staff / staff123   (Staff)

 DATA FILES: created automatically in a folder called "data" next to this file.
             Each file is plain text with one record per line and fields
             separated by the pipe character |   (users.txt, members.txt,
             payments.txt, attendance.txt, audit.txt)

 HOW THIS FILE IS ORGANIZED (good outline for your defense):
   1. Settings and constants
   2. Small helper functions (dates, text cleaning, money)
   3. Record classes (User, Member, Payment, Attendance, AuditEntry)
   4. GymData  - ALL the business logic + saving/loading text files
                 (no Tkinter code here, so the rules are easy to explain)
   5. PDF export helper (tiny PDF writer, no libraries needed)
   6. UI helper functions (buttons, cards, tables, dialogs)
   7. Pages: Login, Dashboard, Log Attendance, Member Records, Reports,
             User Profile, Manage Users, Audit Logs
   8. App - the main window with the top bar, sidebar and page switching
===============================================================================
"""

import calendar
import csv
import datetime
import hashlib
import os
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# =============================================================================
# 1. SETTINGS AND CONSTANTS
# =============================================================================
APP_NAME = "IronCore Fitness"
APP_SUBTITLE = "Gym Membership and Attendance Management System"
APP_VERSION = "1.0"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

SESSION_TIMEOUT_SECONDS = 15 * 60   # auto-logout after 15 minutes of no activity
EXPIRING_SOON_DAYS = 7              # "Expiring Soon" = 7 days or fewer left
MAX_LOGIN_ATTEMPTS = 3              # failed logins before a short lock
LOCKOUT_SECONDS = 30                # how long the login button stays locked
PAGE_SIZE = 8                       # rows per page in Member Records

# Plan name -> (number of months, price in PHP)
PLANS = {
    "Monthly": (1, 800.0),
    "Quarterly": (3, 2000.0),
    "Annual": (12, 5000.0),
}
PAYMENT_METHODS = ["Cash", "GCash", "Bank Transfer"]

# --- Colors (taken from the wireframes) ---
NAVY = "#0B2A5B"        # sidebar, primary buttons, brand text
NAVY_DARK = "#071C3F"
BLUE = "#2F6FD0"        # active sidebar item, links
BG = "#F3F5F9"          # page background
WHITE = "#FFFFFF"
BORDER = "#D5DAE3"
DARK = "#1F2937"
GRAY = "#6B7280"
HEAD_BG = "#E8F0FB"     # table header background
RED = "#C62828"
STATUS_COLORS = {
    "Active": "#1E8E3E",
    "Paid": "#1E8E3E",
    "Expiring Soon": "#E8890C",
    "Expired": "#D32F2F",
    "Inactive": "#6B7280",
}

# --- Fonts (Segoe UI is the normal Windows font) ---
FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_SMALL = ("Segoe UI", 9)
FONT_H2 = ("Segoe UI", 11, "bold")
FONT_TITLE = ("Segoe UI", 20, "bold")
FONT_STAT = ("Segoe UI", 24, "bold")


# =============================================================================
# 2. SMALL HELPER FUNCTIONS
# =============================================================================
def clean(text):
    """Make text safe to store: no pipe characters or line breaks.
    (The pipe | is our field separator, so it must never appear inside data.)"""
    return str(text).replace("|", "/").replace("\n", " ").replace("\r", " ").strip()


def parse_date(text):
    """Turn 'YYYY-MM-DD' text into a date. Returns None if it is not valid."""
    try:
        return datetime.datetime.strptime(str(text).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def iso(d):
    """date -> 'YYYY-MM-DD' (the format used inside the text files)."""
    return d.strftime("%Y-%m-%d")


def pretty(d):
    """date -> 'Oct 04, 2026' (the format shown on screen, like the wireframe)."""
    return d.strftime("%b %d, %Y")


def add_months(d, months):
    """Add whole months to a date. Jan 31 + 1 month -> Feb 28/29 (never overflows)."""
    total = d.year * 12 + (d.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return datetime.date(year, month, day)


def money(amount):
    """1234.5 -> 'PHP 1,234.50' and 800.0 -> 'PHP 800'."""
    if float(amount) == int(amount):
        return "PHP {:,}".format(int(amount))
    return "PHP {:,.2f}".format(amount)


def valid_password(password):
    """Password rule from the proposal: at least 8 characters with a number."""
    return len(password) >= 8 and any(ch.isdigit() for ch in password)


def hash_password(password, salt=None):
    """Return 'salt$hash'. We never store the real password.
    A random salt makes two users with the same password look different.
    PBKDF2 is a slow, standard hashing method that ships with Python."""
    if salt is None:
        salt = os.urandom(8).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 60000)
    return salt + "$" + digest.hex()


def check_password(password, stored):
    """True if the typed password matches the stored 'salt$hash'."""
    if "$" not in stored:
        return False
    salt = stored.split("$", 1)[0]
    return hash_password(password, salt) == stored


# =============================================================================
# 3. RECORD CLASSES  (one class per text file)
#    Each class can turn itself into a list of fields (to_fields) for saving.
# =============================================================================
class User:
    def __init__(self, user_id, full_name, username, password_hash, role,
                 active=True, contact="", email=""):
        self.id = int(user_id)
        self.full_name = full_name
        self.username = username
        self.password_hash = password_hash
        self.role = role            # "Admin" or "Staff"
        self.active = active
        self.contact = contact
        self.email = email

    def to_fields(self):
        return [self.id, self.full_name, self.username, self.password_hash, self.role,
                1 if self.active else 0, self.contact, self.email]


class Member:
    def __init__(self, member_id, name, contact, address, birthdate, gender,
                 em_name, em_contact, plan, start, expiry, registered, active=True):
        self.id = member_id
        self.name = name
        self.contact = contact
        self.address = address
        self.birthdate = birthdate
        self.gender = gender
        self.em_name = em_name
        self.em_contact = em_contact
        self.plan = plan
        self.start = start          # date
        self.expiry = expiry        # date
        self.registered = registered
        self.active = active        # False = deactivated by the Admin

    def to_fields(self):
        return [self.id, self.name, self.contact, self.address, self.birthdate, self.gender,
                self.em_name, self.em_contact, self.plan, iso(self.start), iso(self.expiry),
                iso(self.registered), 1 if self.active else 0]


class Payment:
    def __init__(self, pay_id, member_id, pay_type, amount, date, method, ref, by, note=""):
        self.id = int(pay_id)
        self.member_id = member_id  # empty for a daily sessioner
        self.type = pay_type        # "Membership" or "Daily Session"
        self.amount = float(amount)
        self.date = date
        self.method = method
        self.ref = ref
        self.by = by                # username who encoded it
        self.note = note            # visitor name for daily sessions

    def to_fields(self):
        return [self.id, self.member_id, self.type, self.amount, iso(self.date),
                self.method, self.ref, self.by, self.note]


class Attendance:
    def __init__(self, att_id, member_id, visitor, visitor_contact, att_type,
                 date, time_in, status, by):
        self.id = int(att_id)
        self.member_id = member_id          # empty for a daily sessioner
        self.visitor = visitor              # name of the daily sessioner
        self.visitor_contact = visitor_contact
        self.type = att_type                # "Member" or "Daily"
        self.date = date
        self.time_in = time_in
        self.status = status                # membership status AT THE TIME of entry
        self.by = by

    def to_fields(self):
        return [self.id, self.member_id, self.visitor, self.visitor_contact, self.type,
                iso(self.date), self.time_in, self.status, self.by]


class AuditEntry:
    def __init__(self, entry_id, user, action, details, stamp):
        self.id = int(entry_id)
        self.user = user
        self.action = action
        self.details = details
        self.stamp = stamp

    def to_fields(self):
        return [self.id, self.user, self.action, self.details, self.stamp]


# =============================================================================
# 4. GymData - THE "BRAIN" OF THE SYSTEM
#    Holds all records in memory, applies the business rules, and saves/loads
#    the pipe-delimited text files. Rule violations raise ValueError (or
#    PermissionError); the screens catch them and show a friendly message.
# =============================================================================
class GymData:
    def __init__(self, data_dir=DATA_DIR):
        self.data_dir = data_dir
        self.users = []
        self.members = []
        self.payments = []
        self.attendance = []
        self.audit_log = []
        self.current_user = None
        self.date_offset = 0        # demo helper: shifts "today" to show expiry
        self.load_all()
        if not self.users:          # first run ever -> create sample data
            self.seed_sample_data()

    # ------------------------------------------------------------------ time
    def today(self):
        return datetime.date.today() + datetime.timedelta(days=self.date_offset)

    def now_time(self):
        return datetime.datetime.now().strftime("%I:%M %p")

    def now_stamp(self):
        return pretty(self.today()) + " " + self.now_time()

    # ------------------------------------------------------- saving / loading
    def _path(self, filename):
        return os.path.join(self.data_dir, filename)

    def _write_file(self, filename, records):
        """Write one record per line. We write to a temp file first and then
        swap it in, so a crash while saving can never leave a half-written file."""
        os.makedirs(self.data_dir, exist_ok=True)
        temp_path = self._path(filename) + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            for record in records:
                f.write("|".join(clean(x) if isinstance(x, str) else str(x)
                                 for x in record.to_fields()) + "\n")
        os.replace(temp_path, self._path(filename))

    def _read_file(self, filename, min_fields):
        """Read a file into a list of field-lists. Short lines are padded."""
        rows = []
        if not os.path.exists(self._path(filename)):
            return rows
        with open(self._path(filename), "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                parts = line.split("|")
                while len(parts) < min_fields:
                    parts.append("")
                rows.append(parts)
        return rows

    def save_all(self):
        self._write_file("users.txt", self.users)
        self._write_file("members.txt", self.members)
        self._write_file("payments.txt", self.payments)
        self._write_file("attendance.txt", self.attendance)
        self._write_file("audit.txt", self.audit_log)

    def load_all(self):
        fallback = datetime.date.today()
        for p in self._read_file("users.txt", 8):
            try:
                self.users.append(User(p[0], p[1], p[2], p[3], p[4], p[5] == "1", p[6], p[7]))
            except ValueError:
                pass                # skip a damaged line instead of crashing
        for p in self._read_file("members.txt", 13):
            self.members.append(Member(
                p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8],
                parse_date(p[9]) or fallback, parse_date(p[10]) or fallback,
                parse_date(p[11]) or fallback, p[12] == "1"))
        for p in self._read_file("payments.txt", 9):
            try:
                self.payments.append(Payment(p[0], p[1], p[2], p[3], parse_date(p[4]) or fallback,
                                             p[5], p[6], p[7], p[8]))
            except ValueError:
                pass
        for p in self._read_file("attendance.txt", 9):
            try:
                self.attendance.append(Attendance(p[0], p[1], p[2], p[3], p[4],
                                                  parse_date(p[5]) or fallback, p[6], p[7], p[8]))
            except ValueError:
                pass
        for p in self._read_file("audit.txt", 5):
            try:
                self.audit_log.append(AuditEntry(p[0], p[1], p[2], p[3], p[4]))
            except ValueError:
                pass

    # ----------------------------------------------------------- sample data
    def seed_sample_data(self):
        """Runs only the very first time, so the demo is never empty.
        Start dates are relative to today, so some members are always
        Active, some Expiring Soon and one is already Expired."""
        self.users.append(User(1, "R. Mendoza", "admin", hash_password("admin123"), "Admin"))
        self.users.append(User(2, "Front Desk", "staff", hash_password("staff123"), "Staff"))
        today = datetime.date.today()
        samples = [  # id, name, contact, plan, days since start, address
            ("M-0001", "Juan Dela Cruz", "0917-123-4567", "Monthly", -10, "123 Main St, Manila"),
            ("M-0002", "Maria Santos", "0918-234-5678", "Quarterly", -60, "45 Rizal Ave, Angono"),
            ("M-0003", "Pedro Reyes", "0919-345-6789", "Annual", -100, "9 Mabini St, Taytay"),
            ("M-0004", "Ana Lim", "0920-456-7890", "Monthly", -27, "88 Bonifacio St, Cainta"),
            ("M-0005", "Carlo Bautista", "0921-567-8901", "Quarterly", -85, "17 Luna St, Antipolo"),
            ("M-0006", "Liza Mendoza", "0922-678-9012", "Monthly", -90, "5 Aguinaldo St, Pasig"),
        ]
        for number, (mid, name, contact, plan, offset, address) in enumerate(samples, start=1):
            start = today + datetime.timedelta(days=offset)
            expiry = add_months(start, PLANS[plan][0])
            self.members.append(Member(mid, name, contact, address, "", "", "Emergency Contact",
                                       "0999-000-0000", plan, start, expiry,
                                       today - datetime.timedelta(days=400)))
            # one starter payment per member so the payment history is not empty
            self.payments.append(Payment(number, mid, "Membership", PLANS[plan][1], start,
                                         "Cash", "REF-%03d" % number, "admin"))
        self.audit("Seed Data", "Sample users and members created", user="system")
        self.save_all()

    # ------------------------------------------------------------- audit log
    def audit(self, action, details, user=None):
        """FR-10: every important action is recorded with who/what/when."""
        if user is None:
            user = self.current_user.username if self.current_user else "system"
        entry_id = max([a.id for a in self.audit_log] + [0]) + 1
        self.audit_log.append(AuditEntry(entry_id, user, action, clean(details), self.now_stamp()))

    # ----------------------------------------------------------- permissions
    def is_admin(self):
        return self.current_user is not None and self.current_user.role == "Admin"

    def require_admin(self):
        if not self.is_admin():
            raise PermissionError("Access denied: this function is for the Admin only.")

    def username(self):
        return self.current_user.username if self.current_user else "system"

    # ------------------------------------------------------- login / logout
    def find_user(self, username):
        for u in self.users:
            if u.username.lower() == username.strip().lower():
                return u
        return None

    def login(self, username, password):
        """FR-01. Returns the User, or raises ValueError with the error text."""
        user = self.find_user(username)
        if user and check_password(password, user.password_hash):
            if not user.active:
                self.audit("Failed Login", "Deactivated account", user=user.username)
                self.save_all()
                raise ValueError("This account is deactivated. Contact the Admin.")
            self.current_user = user
            self.audit("Login", "Successful login")
            self.save_all()
            return user
        self.audit("Failed Login", "Wrong username or password", user=username.strip() or "unknown")
        self.save_all()
        raise ValueError("Invalid username or password")

    def logout(self, reason="User logged out"):
        if self.current_user:
            self.audit("Logout" if reason == "User logged out" else "Session Timeout", reason)
            self.save_all()
        self.current_user = None

    # --------------------------------------------------- member look-ups
    def find_member(self, member_id):
        for m in self.members:
            if m.id.lower() == str(member_id).strip().lower():
                return m
        return None

    def search_members(self, text):
        """FR-08: match on name, member ID or contact number (not case sensitive)."""
        text = text.strip().lower()
        if not text:
            return list(self.members)
        return [m for m in self.members
                if text in m.name.lower() or text in m.id.lower() or text in m.contact.lower()]

    def status_of(self, member):
        """FR-06: the status is COMPUTED from the expiry date every time,
        so it is always up to date and never needs manual changes."""
        if not member.active:
            return "Inactive"
        days_left = (member.expiry - self.today()).days
        if days_left < 0:
            return "Expired"
        if days_left <= EXPIRING_SOON_DAYS:
            return "Expiring Soon"
        return "Active"

    def days_left(self, member):
        return (member.expiry - self.today()).days

    def next_member_id(self):
        highest = 0
        for m in self.members:
            try:
                highest = max(highest, int(m.id.split("-")[1]))
            except (IndexError, ValueError):
                pass
        return "M-%04d" % (highest + 1)

    def member_name(self, member_id):
        m = self.find_member(member_id)
        return m.name if m else member_id

    # ---------------------------------------------- FR-02: register a member
    def register_member(self, name, contact, address, birthdate, gender, em_name, em_contact):
        name, contact, em_name, em_contact = clean(name), clean(contact), clean(em_name), clean(em_contact)
        if not name or not contact or not em_name or not em_contact:
            raise ValueError("Full name, contact number and emergency contact name/number are required.")
        birthdate = clean(birthdate)
        if birthdate and parse_date(birthdate) is None:
            raise ValueError("Birthdate must be in YYYY-MM-DD format (or leave it blank).")
        for m in self.members:      # duplicate check: same name AND same contact
            if m.name.lower() == name.lower() and m.contact == contact:
                self.audit("Duplicate Rejected", name)
                self.save_all()
                raise ValueError("Duplicate rejected: %s already has this name and contact number." % m.id)
        today = self.today()
        # A new member has not paid yet, so we make the membership "expired
        # yesterday". It becomes Active once the first payment is recorded.
        member = Member(self.next_member_id(), name, contact, clean(address), birthdate, clean(gender),
                        em_name, em_contact, "Monthly", today, today - datetime.timedelta(days=1), today)
        self.members.append(member)
        self.audit("Add Member", "Added %s %s" % (member.id, member.name))
        self.save_all()
        return member

    def edit_member(self, member, contact, address, em_name, em_contact):
        """Admin only. Changes contact details (not the name or plan)."""
        self.require_admin()
        contact, em_name, em_contact = clean(contact), clean(em_name), clean(em_contact)
        if not contact or not em_name or not em_contact:
            raise ValueError("Contact number and emergency contact are required.")
        old = member.contact
        member.contact, member.address = contact, clean(address)
        member.em_name, member.em_contact = em_name, em_contact
        self.audit("Edit Member", "Updated %s (contact %s -> %s)" % (member.id, old, contact))
        self.save_all()

    def set_member_active(self, member, active):
        """Admin only. Deactivate/reactivate instead of deleting (history is kept)."""
        self.require_admin()
        member.active = active
        self.audit("Reactivate Member" if active else "Deactivate Member", "%s %s" % (member.id, member.name))
        self.save_all()

    # ------------------------------------------- FR-03 / FR-04: payments
    def plan_period(self, member, plan):
        """Work out the new (start, expiry) for a payment.
        - Still valid  -> renew EARLY: the new period continues from the OLD expiry
                          so the member does not lose any paid days.
        - Expired/new  -> the new period starts TODAY."""
        today = self.today()
        still_valid = member.active and member.expiry >= today
        base = member.expiry if still_valid else today
        start = member.start if still_valid else today
        return start, add_months(base, PLANS[plan][0])

    def record_membership_payment(self, member, plan, method, ref):
        if plan not in PLANS:
            raise ValueError("Please choose a plan.")
        ref = clean(ref)
        if method != "Cash" and not ref:
            raise ValueError("A reference number is required for GCash and Bank Transfer.")
        # First membership payment = "Activate", any later one = "Renew" (for the audit log)
        was_renewal = any(p.member_id == member.id and p.type == "Membership" for p in self.payments)
        start, expiry = self.plan_period(member, plan)
        member.start, member.expiry, member.plan, member.active = start, expiry, plan, True
        amount = PLANS[plan][1]
        payment = Payment(self._next_payment_id(), member.id, "Membership", amount, self.today(),
                          method, ref, self.username())
        self.payments.append(payment)
        self.audit("Record Payment", "%s (Membership) for %s" % (money(amount), member.id))
        self.audit("Renew Membership" if was_renewal else "Activate Membership",
                   "%s %s until %s" % (member.id, plan, iso(expiry)))
        self.save_all()
        return payment

    def _next_payment_id(self):
        return max([p.id for p in self.payments] + [0]) + 1

    # ------------------------------------------------- FR-05: attendance
    def checked_in_today(self, member_id):
        """Returns today's attendance record for this member, or None."""
        for a in self.attendance:
            if a.member_id == member_id and a.date == self.today():
                return a
        return None

    def log_member_attendance(self, member):
        """Saves the visit with the status the member had AT THAT MOMENT."""
        record = Attendance(self._next_attendance_id(), member.id, "", "", "Member", self.today(),
                            self.now_time(), self.status_of(member), self.username())
        self.attendance.append(record)
        self.audit("Log Attendance", "Checked in %s %s" % (member.id, member.name))
        self.save_all()
        return record

    def log_daily_session(self, name, contact, amount_text, method, ref):
        """A walk-in visitor: no membership, just a name and the fee paid."""
        name, contact, ref = clean(name), clean(contact), clean(ref)
        if not name:
            raise ValueError("Visitor name is required.")
        try:
            amount = float(amount_text.replace(",", ""))
        except ValueError:
            raise ValueError("Amount paid must be a number.")
        if amount <= 0:
            raise ValueError("Amount paid must be greater than 0.")
        if method != "Cash" and not ref:
            raise ValueError("A reference number is required for GCash and Bank Transfer.")
        record = Attendance(self._next_attendance_id(), "", name, contact, "Daily", self.today(),
                            self.now_time(), "Paid", self.username())
        self.attendance.append(record)
        self.payments.append(Payment(self._next_payment_id(), "", "Daily Session", amount,
                                     self.today(), method, ref, self.username(), name))
        self.audit("Log Attendance", "Daily sessioner " + name)
        self.audit("Record Payment", "%s (Daily Session) daily sessioner" % money(amount))
        self.save_all()
        return record

    def _next_attendance_id(self):
        return max([a.id for a in self.attendance] + [0]) + 1

    def attendance_name(self, record):
        return record.visitor if record.type == "Daily" else self.member_name(record.member_id)

    def payment_name(self, payment):
        return payment.note if payment.member_id == "" else self.member_name(payment.member_id)

    # ----------------------------------------------------- FR-07: reports
    # Each report returns a dictionary:
    #   title, columns, rows (list of lists of text), summary (3 label/value pairs),
    #   total_row (optional last row)
    def report_payments(self, d_from, d_to, query=""):
        self.require_admin()
        query = query.strip().lower()
        rows, total, unique = [], 0.0, set()
        for p in sorted(self.payments, key=lambda x: (x.date, x.id), reverse=True):
            name = self.payment_name(p)
            if not (d_from <= p.date <= d_to):
                continue
            if query and query not in p.member_id.lower() and query not in name.lower():
                continue
            rows.append([pretty(p.date), p.member_id or "-", name, money(p.amount),
                         p.method, p.ref or "-", p.by])
            total += p.amount
            if p.member_id:
                unique.add(p.member_id)
        return {
            "title": "Payment and Income Report (%s to %s)" % (pretty(d_from), pretty(d_to)),
            "columns": ["Date", "Member ID", "Name", "Amount", "Method", "Reference No.", "Encoded By"],
            "rows": rows,
            "summary": [("Total Payments", str(len(rows))), ("Total Income", money(total)),
                        ("Unique Members", str(len(unique)))],
            "total_row": ["", "", "Total", money(total), "", "", ""],
        }

    def report_attendance(self, d_from, d_to, query=""):
        self.require_admin()
        query = query.strip().lower()
        rows, members, daily = [], 0, 0
        for a in sorted(self.attendance, key=lambda x: (x.date, x.id), reverse=True):
            name = self.attendance_name(a)
            if not (d_from <= a.date <= d_to):
                continue
            if query and query not in a.member_id.lower() and query not in name.lower():
                continue
            rows.append([pretty(a.date), a.time_in, a.member_id or "-", name, a.type, a.status, a.by])
            if a.type == "Member":
                members += 1
            else:
                daily += 1
        return {
            "title": "Attendance Report (%s to %s)" % (pretty(d_from), pretty(d_to)),
            "columns": ["Date", "Time In", "Member ID", "Name", "Type", "Status", "Logged By"],
            "rows": rows,
            "summary": [("Total Visits", str(len(rows))), ("Member Visits", str(members)),
                        ("Daily Sessioners", str(daily))],
            "total_row": None,
        }

    def report_membership(self, query=""):
        self.require_admin()
        query = query.strip().lower()
        rows, counts = [], {"Active": 0, "Expiring Soon": 0, "Expired": 0, "Inactive": 0}
        for m in self.members:
            if query and query not in m.id.lower() and query not in m.name.lower():
                continue
            status = self.status_of(m)
            counts[status] += 1
            rows.append([m.id, m.name, m.contact, m.plan, pretty(m.start), pretty(m.expiry), status])
        return {
            "title": "Membership Status Report (as of %s)" % pretty(self.today()),
            "columns": ["Member ID", "Name", "Contact Number", "Plan", "Start Date", "Expiry Date", "Status"],
            "rows": rows,
            "summary": [("Total Members", str(len(rows))),
                        ("Active (incl. Expiring Soon)", str(counts["Active"] + counts["Expiring Soon"])),
                        ("Expired / Inactive", str(counts["Expired"] + counts["Inactive"]))],
            "total_row": None,
        }

    # ------------------------------------------------ FR-09: user accounts
    def create_staff(self, full_name, username, password):
        self.require_admin()
        full_name, username = clean(full_name), clean(username)
        if not full_name or not username:
            raise ValueError("Full name and username are required.")
        if self.find_user(username):
            raise ValueError("That username already exists.")
        if not valid_password(password):
            raise ValueError("Password must be at least 8 characters and contain a number.")
        user = User(max([u.id for u in self.users] + [0]) + 1, full_name, username,
                    hash_password(password), "Staff")
        self.users.append(user)
        self.audit("Create User", "Created staff " + username)
        self.save_all()

    def toggle_user_active(self, user):
        self.require_admin()
        if user is self.current_user:
            raise ValueError("You cannot deactivate your own account.")
        user.active = not user.active
        self.audit("Activate User" if user.active else "Deactivate User", user.username)
        self.save_all()

    def reset_password(self, user, new_password):
        self.require_admin()
        if not valid_password(new_password):
            raise ValueError("Password must be at least 8 characters and contain a number.")
        user.password_hash = hash_password(new_password)
        self.audit("Reset Password", user.username)
        self.save_all()

    def update_profile(self, full_name, contact, email):
        full_name = clean(full_name)
        if not full_name:
            raise ValueError("Full name is required.")
        u = self.current_user
        u.full_name, u.contact, u.email = full_name, clean(contact), clean(email)
        self.audit("Update Profile", "Changed account information")
        self.save_all()

    def change_password(self, current, new, confirm):
        u = self.current_user
        if not check_password(current, u.password_hash):
            raise ValueError("Current password is incorrect.")
        if not valid_password(new):
            raise ValueError("New password must be at least 8 characters and contain a number.")
        if new != confirm:
            raise ValueError("New password and confirmation do not match.")
        u.password_hash = hash_password(new)
        self.audit("Change Password", "Own password changed")
        self.save_all()

    def user_activity(self, username, limit=8):
        mine = [a for a in self.audit_log if a.user == username]
        return list(reversed(mine))[:limit]

    # ----------------------------------------------------- demo date helper
    def set_demo_offset(self, days):
        self.require_admin()
        self.date_offset = days
        self.audit("Demo Date Shift", "System date is now %s (offset %d days)" % (iso(self.today()), days))
        self.save_all()


# =============================================================================
# 5. PDF EXPORT HELPER
#    Python has no built-in PDF writer, so this tiny one writes a plain-text
#    table (Courier font) into a valid PDF by hand. No libraries needed.
# =============================================================================
def write_simple_pdf(path, title, subtitle_lines, columns, rows):
    # 1) Work out how wide each column should be (max 26 characters).
    widths = []
    for i, col in enumerate(columns):
        longest = max([len(str(col))] + [len(str(r[i])) for r in rows])
        widths.append(min(longest, 26))

    def format_row(values):
        return "  ".join(str(v)[:w].ljust(w) for v, w in zip(values, widths))

    # 2) Build every text line of the document.
    lines = [title] + subtitle_lines + ["", format_row(columns), "-" * len(format_row(columns))]
    lines += [format_row(r) for r in rows]
    if not rows:
        lines.append("(no records)")

    # 3) Pick a font size so the widest line fits the page (Courier letters are
    #    0.6 x the font size wide), then split the lines into landscape A4 pages.
    widest = max(len(line) for line in lines)
    size = max(5.0, min(8.0, 760 / (0.6 * widest)))
    leading = size + 3
    per_page = int(500 / leading)
    pages = [lines[i:i + per_page] for i in range(0, len(lines), per_page)] or [[]]

    def escape(text):  # characters that have a special meaning inside a PDF string
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    # 4) Build the PDF objects. 1=catalog 2=page list 3=font, then page/content pairs.
    kids = " ".join("%d 0 R" % (4 + 2 * i) for i in range(len(pages)))
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               ("<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(pages))).encode(),
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>"]
    for i, page_lines in enumerate(pages):
        text = "BT /F1 %.1f Tf %.1f TL 40 555 Td\n" % (size, leading)
        for line in page_lines:
            text += "(%s) Tj T*\n" % escape(line)
        text += "(Page %d of %d) Tj\nET" % (i + 1, len(pages))
        stream = text.encode("latin-1", "replace")
        objects.append(("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] "
                        "/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>"
                        % (5 + 2 * i)).encode())
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")

    # 5) Write the file with its cross-reference table.
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += ("%d 0 obj\n" % number).encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += ("xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)).encode()
    for offset in offsets:
        out += ("%010d 00000 n \n" % offset).encode()
    out += ("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objects) + 1, xref_at)).encode()
    with open(path, "wb") as f:
        f.write(out)


# =============================================================================
# 6. UI HELPER FUNCTIONS  (small building blocks used by every page)
# =============================================================================
def make_button(parent, text, command, kind="primary", width=None):
    """kind: 'primary' (navy), 'outline' (white with navy border), 'danger' (red)."""
    if kind == "primary":
        bg, fg, hover = NAVY, WHITE, "#14408A"
    elif kind == "danger":
        bg, fg, hover = RED, WHITE, "#9F1F1F"
    else:
        bg, fg, hover = WHITE, NAVY, HEAD_BG
    btn = tk.Button(parent, text=text, command=command, font=FONT_BOLD, bg=bg, fg=fg,
                    activebackground=hover, activeforeground=fg, relief="flat", bd=0,
                    padx=14, pady=5, cursor="hand2", width=width,
                    highlightthickness=1, highlightbackground=NAVY if kind != "danger" else RED)
    return btn


def make_link(parent, text, command, bg=WHITE):
    """A clickable blue text link (like 'View All' in the wireframe)."""
    return tk.Button(parent, text=text, command=command, font=FONT_BOLD, fg=BLUE, bg=bg,
                     activeforeground=NAVY, activebackground=bg, relief="flat", bd=0,
                     cursor="hand2", highlightthickness=0)


def make_entry(parent, var=None, width=24, show="", readonly=False):
    entry = tk.Entry(parent, textvariable=var, width=width, show=show, font=FONT, relief="flat",
                     bg=WHITE, fg=DARK, insertbackground=DARK, highlightthickness=1,
                     highlightbackground=BORDER, highlightcolor=BLUE)
    if readonly:
        entry.config(state="readonly", readonlybackground="#EEF0F4")
    return entry


def make_combo(parent, var, values, width=20):
    return ttk.Combobox(parent, textvariable=var, values=values, state="readonly", width=width, font=FONT)


def make_card(parent, title=None, bg=WHITE, border=BORDER):
    """A white box with a thin border (every panel in the wireframes is one)."""
    card = tk.Frame(parent, bg=bg, highlightthickness=1, highlightbackground=border)
    if title:
        tk.Label(card, text=title, font=FONT_H2, bg=bg, fg=DARK).pack(anchor="w", padx=14, pady=(10, 4))
    return card


def make_label(parent, text, bold=False, color=DARK, bg=WHITE, size=None):
    font = FONT_BOLD if bold else FONT
    if size:
        font = ("Segoe UI", size, "bold" if bold else "normal")
    return tk.Label(parent, text=text, font=font, fg=color, bg=bg)


def make_badge(parent, status):
    """The small colored status chip (Active / Expiring Soon / Expired)."""
    badge = tk.Label(parent, font=FONT_SMALL, fg=WHITE, padx=8, pady=1)
    set_badge(badge, status)
    return badge


def set_badge(badge, status):
    badge.config(text=status or "", bg=STATUS_COLORS.get(status, GRAY) if status else WHITE)


def make_photo_placeholder(parent, width=90, height=70, bg=WHITE):
    """The grey box with an X that the wireframes use for a photo."""
    canvas = tk.Canvas(parent, width=width, height=height, bg="#E5E7EB", highlightthickness=1,
                       highlightbackground=BORDER)
    canvas.create_line(0, 0, width, height, fill="#B8BDC7")
    canvas.create_line(0, height, width, 0, fill="#B8BDC7")
    return canvas


def make_table(parent, columns, widths, height=8):
    """A table (ttk.Treeview) with a scrollbar. Returns (frame, tree)."""
    frame = tk.Frame(parent, bg=WHITE)
    tree = ttk.Treeview(frame, columns=columns, show="headings", height=height, selectmode="browse")
    y_scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    x_scroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)

    def on_x_scroll(first, last):
        """Show the sideways scrollbar ONLY when the columns do not fit."""
        x_scroll.set(first, last)
        if float(first) <= 0.0 and float(last) >= 1.0:
            x_scroll.grid_remove()
        else:
            x_scroll.grid()
    tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=on_x_scroll)
    set_table_columns(tree, columns, widths)
    tree.grid(row=0, column=0, sticky="nsew")
    y_scroll.grid(row=0, column=1, sticky="ns")
    x_scroll.grid(row=1, column=0, sticky="ew")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    for status, color in STATUS_COLORS.items():          # row text colors per status
        tree.tag_configure("st_" + status.replace(" ", "_"), foreground=color)
    tree.tag_configure("total", font=FONT_BOLD, background=HEAD_BG)
    return frame, tree


def set_table_columns(tree, columns, widths):
    tree.config(columns=columns)
    for col, width in zip(columns, widths):
        tree.heading(col, text=col, anchor="w")
        # width = normal size; minwidth = never squeeze a column below it
        # (if the window is too small, the table scrolls sideways instead of cutting text)
        tree.column(col, width=width, minwidth=width, anchor="w", stretch=True)


def fill_table(tree, rows, status_col=None, iids=None, total_row=None):
    """Replace the table contents. status_col = index of the Status column
    (that row's text is colored to match). iids = unique id for each row."""
    tree.delete(*tree.get_children())
    for i, row in enumerate(rows):
        tag = ()
        if status_col is not None:
            tag = ("st_" + str(row[status_col]).replace(" ", "_"),)
        tree.insert("", "end", iid=iids[i] if iids else None, values=row, tags=tag)
    if total_row:
        tree.insert("", "end", values=total_row, tags=("total",))


def center_window(window, parent):
    """Put a pop-up window in the middle of the main window."""
    window.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - window.winfo_width()) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - window.winfo_height()) // 3
    window.geometry("+%d+%d" % (max(x, 0), max(y, 0)))


class StatCard(tk.Frame):
    """One of the four number boxes on the dashboard."""
    def __init__(self, parent, title, highlight=False):
        bg = "#FFF7E6" if highlight else WHITE
        border = "#E8890C" if highlight else BORDER
        super().__init__(parent, bg=bg, highlightthickness=1, highlightbackground=border)
        self.title = tk.Label(self, text=title, font=FONT_SMALL, fg="#B45F06" if highlight else GRAY, bg=bg)
        self.title.pack(anchor="w", padx=14, pady=(10, 0))
        self.value = tk.Label(self, text="0", font=FONT_STAT, fg=DARK, bg=bg)
        self.value.pack(anchor="w", padx=14, pady=(0, 8))

    def set(self, title, value):
        self.title.config(text=title)
        self.value.config(text=value)


class FormDialog(tk.Toplevel):
    """A reusable pop-up form. 'fields' is a list of tuples:
         (key, label, kind, default, values)
       kind is 'text', 'password', 'combo' or 'readonly'.
       on_submit(values_dict) does the work and may raise ValueError to show an error."""
    def __init__(self, app, title, fields, on_submit, submit_text="Save", intro=None):
        super().__init__(app, bg=WHITE)
        self.title(title)
        self.transient(app)
        self.resizable(False, False)
        self.on_submit = on_submit
        self.vars = {}
        body = tk.Frame(self, bg=WHITE, padx=22, pady=16)
        body.pack()
        row = 0
        if intro:
            tk.Label(body, text=intro, font=FONT, fg=GRAY, bg=WHITE, justify="left",
                     wraplength=380).grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 10))
            row += 1
        first_entry = None
        for key, label, kind, default, values in fields:
            tk.Label(body, text=label, font=FONT, fg=DARK, bg=WHITE).grid(
                row=row, column=0, sticky="w", pady=4, padx=(0, 12))
            var = tk.StringVar(value=default)
            self.vars[key] = var
            if kind == "combo":
                widget = make_combo(body, var, values, width=28)
            else:
                widget = make_entry(body, var, width=31, show="*" if kind == "password" else "",
                                    readonly=(kind == "readonly"))
            widget.grid(row=row, column=1, sticky="ew", pady=4, ipady=3)
            if first_entry is None and kind in ("text", "password"):
                first_entry = widget
            row += 1
        self.error = tk.Label(body, text="", font=FONT_SMALL, fg=RED, bg=WHITE, wraplength=380, justify="left")
        self.error.grid(row=row, column=0, columnspan=2, sticky="w", pady=(6, 0))
        buttons = tk.Frame(body, bg=WHITE)
        buttons.grid(row=row + 1, column=0, columnspan=2, sticky="e", pady=(10, 0))
        make_button(buttons, "Cancel", self.destroy, "outline").pack(side="right", padx=(8, 0))
        make_button(buttons, submit_text, self.submit).pack(side="right")
        self.bind("<Return>", lambda e: self.submit())
        self.bind("<Escape>", lambda e: self.destroy())
        center_window(self, app)
        self.grab_set()                 # modal: the main window is locked until closed
        (first_entry or self).focus_set()

    def submit(self):
        values = {key: var.get().strip() for key, var in self.vars.items()}
        try:
            self.on_submit(values)
        except (ValueError, PermissionError) as error:
            self.error.config(text=str(error))
            return
        self.destroy()


class PaymentDialog(tk.Toplevel):
    """Record Payment / Renew Membership. Shows the amount and the new expiry
    date BEFORE the user confirms, so there are no surprises."""
    def __init__(self, app, member, on_done=None):
        super().__init__(app, bg=WHITE)
        self.app, self.data, self.member, self.on_done = app, app.data, member, on_done
        self.title("Record Payment / Renew Membership")
        self.transient(app)
        self.resizable(False, False)
        body = tk.Frame(self, bg=WHITE, padx=22, pady=16)
        body.pack()
        status = self.data.status_of(member)
        make_label(body, "%s  (%s)" % (member.name, member.id), True, size=12).grid(
            row=0, column=0, columnspan=2, sticky="w")
        make_label(body, "Current status: %s   |   Expiry: %s" % (status, pretty(member.expiry)),
                   color=STATUS_COLORS.get(status, GRAY)).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))

        self.plan_var = tk.StringVar(value=member.plan if member.plan in PLANS else "Monthly")
        self.method_var = tk.StringVar(value="Cash")
        self.ref_var = tk.StringVar()
        make_label(body, "Plan").grid(row=2, column=0, sticky="w", pady=4)
        plan_box = make_combo(body, self.plan_var, list(PLANS.keys()), 28)
        plan_box.grid(row=2, column=1, sticky="ew", pady=4, ipady=3)
        plan_box.bind("<<ComboboxSelected>>", lambda e: self.update_preview())
        make_label(body, "Payment method").grid(row=3, column=0, sticky="w", pady=4)
        make_combo(body, self.method_var, PAYMENT_METHODS, 28).grid(row=3, column=1, sticky="ew", pady=4, ipady=3)
        make_label(body, "Reference no.").grid(row=4, column=0, sticky="w", pady=4, padx=(0, 12))
        make_entry(body, self.ref_var, width=31).grid(row=4, column=1, sticky="ew", pady=4, ipady=3)
        make_label(body, "(required for GCash / Bank Transfer)", color=GRAY).grid(row=5, column=1, sticky="w")

        self.preview = tk.Label(body, text="", font=FONT_BOLD, fg=NAVY, bg=HEAD_BG, justify="left",
                                padx=10, pady=8, anchor="w")
        self.preview.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.error = tk.Label(body, text="", font=FONT_SMALL, fg=RED, bg=WHITE, wraplength=380, justify="left")
        self.error.grid(row=7, column=0, columnspan=2, sticky="w", pady=(6, 0))
        buttons = tk.Frame(body, bg=WHITE)
        buttons.grid(row=8, column=0, columnspan=2, sticky="e", pady=(10, 0))
        make_button(buttons, "Cancel", self.destroy, "outline").pack(side="right", padx=(8, 0))
        make_button(buttons, "Confirm Payment", self.confirm).pack(side="right")
        self.update_preview()
        self.bind("<Escape>", lambda e: self.destroy())
        center_window(self, app)
        self.grab_set()

    def update_preview(self):
        plan = self.plan_var.get()
        start, expiry = self.data.plan_period(self.member, plan)
        self.preview.config(text="Amount due: %s\nNew start: %s     New expiry: %s"
                                 % (money(PLANS[plan][1]), pretty(start), pretty(expiry)))

    def confirm(self):
        plan, method = self.plan_var.get(), self.method_var.get()
        if method != "Cash" and not self.ref_var.get().strip():
            self.error.config(text="A reference number is required for GCash and Bank Transfer.")
            return
        if not messagebox.askyesno("Confirm payment", "Record %s (%s) for %s?"
                                   % (money(PLANS[plan][1]), method, self.member.name), parent=self):
            return
        try:
            self.data.record_membership_payment(self.member, plan, method, self.ref_var.get())
        except ValueError as error:
            self.error.config(text=str(error))
            return
        messagebox.showinfo("Payment recorded", "%s is now %s.\nValid until %s."
                            % (self.member.name, self.data.status_of(self.member), pretty(self.member.expiry)),
                            parent=self)
        self.destroy()
        if self.on_done:
            self.on_done()


# =============================================================================
# 7. PAGES
#    Every page is a Frame that fills the area to the right of the sidebar.
#    Each page has reload() which re-reads the data and refreshes the widgets.
# =============================================================================
class Page(tk.Frame):
    """Base class: gives every page the big title on the left and a free
    area on the right of the title for buttons (like in the wireframes)."""
    def __init__(self, parent, app, title):
        super().__init__(parent, bg=BG)
        self.app = app
        self.data = app.data
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", pady=(0, 10))
        tk.Label(header, text=title, font=FONT_TITLE, bg=BG, fg=DARK).pack(side="left")
        self.header_right = tk.Frame(header, bg=BG)
        self.header_right.pack(side="right")
        self.msg = tk.Label(self.header_right, text="", font=FONT_BOLD, bg=BG)
        self._msg_job = None

    def flash(self, text, ok=True):
        """Show a short green/red message at the top right for a few seconds."""
        self.msg.config(text=text, fg=STATUS_COLORS["Active"] if ok else RED)
        self.msg.pack(side="left", padx=(0, 10))
        if self._msg_job:
            self.after_cancel(self._msg_job)
        self._msg_job = self.after(7000, lambda: self.msg.config(text=""))

    def reload(self):
        pass


# ------------------------------------------------------------------ DASHBOARD
class DashboardPage(Page):
    def __init__(self, parent, app):
        super().__init__(parent, app, "Dashboard")
        self.date_label = tk.Label(self.header_right, font=FONT, bg=BG, fg=DARK)
        self.date_label.pack(side="left", padx=(0, 14))
        make_button(self.header_right, "Log Attendance", lambda: app.navigate("Log Attendance")).pack(side="left", padx=4)
        make_button(self.header_right, "Add Member", lambda: app.add_member(self.reload), "outline").pack(side="left", padx=4)

        # Four stat cards in one row
        cards = tk.Frame(self, bg=BG)
        cards.pack(fill="x")
        self.stats = []
        for i, (title, highlight) in enumerate([("Today's Attendance", False), ("Active Members", False),
                                                ("Expiring Soon", True), ("Today's Income", False)]):
            cards.columnconfigure(i, weight=1, uniform="stat")
            card = StatCard(cards, title, highlight)
            card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0 if i == 3 else 6))
            self.stats.append(card)

        # Two tables side by side
        lower = tk.Frame(self, bg=BG)
        lower.pack(fill="both", expand=True, pady=(12, 0))
        lower.columnconfigure(0, weight=3)
        lower.columnconfigure(1, weight=2)
        lower.rowconfigure(0, weight=1)

        left = make_card(lower, "Expiring and Expired Memberships")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        frame, self.exp_tree = make_table(left, ["Member ID", "Name", "Plan", "Expiry Date", "Status"],
                                          [80, 150, 80, 100, 100], height=9)
        frame.pack(fill="both", expand=True, padx=14)
        bar = tk.Frame(left, bg=WHITE)
        bar.pack(fill="x", padx=14, pady=8)
        make_button(bar, "Renew Selected", self.renew_selected, "outline").pack(side="left")
        make_link(bar, "View All", lambda: app.navigate("Member Records")).pack(side="right")

        right = make_card(lower, "Recent Attendance")
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        frame, self.recent_tree = make_table(right, ["Time", "Name", "Type"], [80, 140, 70], height=9)
        frame.pack(fill="both", expand=True, padx=14)
        bar = tk.Frame(right, bg=WHITE)
        bar.pack(fill="x", padx=14, pady=8)
        make_link(bar, "View All", lambda: app.navigate("Log Attendance")).pack(side="left")
        self.reload()

    def reload(self):
        d = self.data
        today = d.today()
        self.date_label.config(text=pretty(today))
        todays = [a for a in d.attendance if a.date == today]
        statuses = [d.status_of(m) for m in d.members]
        income = sum(p.amount for p in d.payments if p.date == today)
        self.stats[0].set("Today's Attendance", str(len(todays)))
        self.stats[1].set("Active Members", str(statuses.count("Active") + statuses.count("Expiring Soon")))
        self.stats[2].set("Expiring Soon", str(statuses.count("Expiring Soon")))
        self.stats[3].set("Today's Income", money(income))

        flagged = [m for m in d.members if d.status_of(m) in ("Expiring Soon", "Expired")]
        flagged.sort(key=lambda m: m.expiry)
        fill_table(self.exp_tree, [[m.id, m.name, m.plan, pretty(m.expiry), d.status_of(m)] for m in flagged],
                   status_col=4, iids=[m.id for m in flagged])
        recent = list(reversed(todays))[:30]
        fill_table(self.recent_tree, [[a.time_in, d.attendance_name(a), a.type] for a in recent])

    def renew_selected(self):
        selected = self.exp_tree.selection()
        if not selected:
            messagebox.showinfo("Renew", "Click a member in the table first.")
            return
        PaymentDialog(self.app, self.data.find_member(selected[0]), self.reload)


# ------------------------------------------------------------- LOG ATTENDANCE
class LogAttendancePage(Page):
    def __init__(self, parent, app):
        super().__init__(parent, app, "Log Attendance")
        self.selected = None            # the Member chosen for check-in
        self.matches = []               # members currently shown in the suggestion list

        # ---- Card 1: Member Check-in
        checkin = make_card(self, "Member Check-in")
        checkin.pack(fill="x")
        body = tk.Frame(checkin, bg=WHITE)
        body.pack(fill="x", padx=14, pady=(0, 12))
        body.columnconfigure(0, weight=1, uniform="half")
        body.columnconfigure(1, weight=1, uniform="half")
        left = tk.Frame(body, bg=WHITE)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        make_label(left, "Search by name, member ID or contact", color=GRAY).pack(anchor="w")
        self.search_var = tk.StringVar()
        self.search_entry = make_entry(left, self.search_var, width=40)
        self.search_entry.pack(fill="x", ipady=4, pady=(2, 0))
        self.suggest = tk.Listbox(left, height=4, font=FONT, relief="flat", bd=0, highlightthickness=1,
                                  highlightbackground=BORDER, selectbackground=HEAD_BG, selectforeground=DARK,
                                  activestyle="none")
        self.suggest.bind("<<ListboxSelect>>", self.pick_suggestion)
        self.search_var.trace_add("write", lambda *a: self.update_suggestions())

        # right side: the member info card
        info = tk.Frame(body, bg=WHITE, highlightthickness=1, highlightbackground=BORDER)
        info.grid(row=0, column=1, sticky="nsew")
        make_photo_placeholder(info, 80, 64).grid(row=0, column=0, rowspan=4, padx=10, pady=10, sticky="n")
        self.info_name = make_label(info, "No member selected", True, size=12)
        self.info_name.grid(row=0, column=1, sticky="w", pady=(10, 0))
        self.info_plan = make_label(info, "Plan: -", color=GRAY)
        self.info_plan.grid(row=1, column=1, sticky="w")
        self.info_expiry = make_label(info, "Expiry: -", color=GRAY)
        self.info_expiry.grid(row=2, column=1, sticky="w")
        self.info_badge = make_badge(info, "")
        self.info_badge.grid(row=3, column=1, sticky="w", pady=(2, 0))
        buttons = tk.Frame(info, bg=WHITE)
        buttons.grid(row=4, column=0, columnspan=2, sticky="w", padx=10, pady=(4, 10))
        make_button(buttons, "Log Attendance", self.log_member).pack(side="left")
        make_button(buttons, "Clear", self.clear_member, "outline").pack(side="left", padx=8)

        # ---- Card 2: Daily Sessioner
        daily = make_card(self, "Daily Sessioner")
        daily.pack(fill="x", pady=10)
        form = tk.Frame(daily, bg=WHITE)
        form.pack(fill="x", padx=14, pady=(0, 12))
        self.d_name, self.d_contact = tk.StringVar(), tk.StringVar()
        self.d_amount, self.d_ref = tk.StringVar(), tk.StringVar()
        self.d_method = tk.StringVar(value="Cash")
        labels = ["Name", "Contact Number (optional)", "Amount Paid", "Payment Method", "Reference No."]
        for i, text in enumerate(labels):
            form.columnconfigure(i, weight=1, uniform="daily")
            make_label(form, text, color=GRAY).grid(row=0, column=i, sticky="w", padx=(0 if i == 0 else 8, 0))
        make_entry(form, self.d_name, 18).grid(row=1, column=0, sticky="ew", ipady=4)
        make_entry(form, self.d_contact, 18).grid(row=1, column=1, sticky="ew", padx=(8, 0), ipady=4)
        make_entry(form, self.d_amount, 12).grid(row=1, column=2, sticky="ew", padx=(8, 0), ipady=4)
        make_combo(form, self.d_method, PAYMENT_METHODS, 14).grid(row=1, column=3, sticky="ew", padx=(8, 0), ipady=3)
        make_entry(form, self.d_ref, 14).grid(row=1, column=4, sticky="ew", padx=(8, 0), ipady=4)
        buttons = tk.Frame(daily, bg=WHITE)
        buttons.pack(anchor="w", padx=14, pady=(0, 12))
        make_button(buttons, "Save Daily Session", self.save_daily).pack(side="left")
        make_button(buttons, "Clear", self.clear_daily, "outline").pack(side="left", padx=8)
        make_label(buttons, "Reference number is required for GCash / Bank Transfer", color=GRAY).pack(side="left", padx=8)

        # ---- Card 3: Today's Attendance table
        today_card = make_card(self)
        today_card.pack(fill="both", expand=True)
        top = tk.Frame(today_card, bg=WHITE)
        top.pack(fill="x", padx=14, pady=(10, 4))
        make_label(top, "Today's Attendance", True, size=11).pack(side="left")
        self.total_label = make_label(top, "Total today: 0", color=GRAY)
        self.total_label.pack(side="left", padx=12)
        self.filter_var = tk.StringVar()
        make_entry(top, self.filter_var, 26).pack(side="right", ipady=3)
        make_label(top, "Filter / Search ", color=GRAY).pack(side="right")
        self.filter_var.trace_add("write", lambda *a: self.reload())
        frame, self.tree = make_table(today_card, ["No.", "Time In", "Name", "Type", "Status", "Logged By"],
                                      [50, 100, 220, 90, 110, 110], height=6)
        frame.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        self.reload()

    # --- member search / selection ---
    def update_suggestions(self):
        text = self.search_var.get().strip()
        self.suggest.pack_forget()
        if not text or (self.selected and text == self.selected_label()):
            return
        self.matches = self.data.search_members(text)[:6]
        self.suggest.delete(0, "end")
        for m in self.matches:
            self.suggest.insert("end", "%s   %s" % (m.name, m.id))
        if self.matches:
            self.suggest.config(height=len(self.matches))
            self.suggest.pack(fill="x")

    def selected_label(self):
        return "%s %s" % (self.selected.name, self.selected.id)

    def pick_suggestion(self, event=None):
        index = self.suggest.curselection()
        if not index:
            return
        self.selected = self.matches[index[0]]
        self.suggest.pack_forget()
        self.search_var.set(self.selected_label())
        self.show_member_info()

    def show_member_info(self):
        m = self.selected
        status = self.data.status_of(m)
        self.info_name.config(text=m.name)
        self.info_plan.config(text="Plan: " + m.plan)
        self.info_expiry.config(text="Expiry: " + pretty(m.expiry))
        set_badge(self.info_badge, status)

    def clear_member(self):
        self.selected = None
        self.search_var.set("")
        self.suggest.pack_forget()
        self.info_name.config(text="No member selected")
        self.info_plan.config(text="Plan: -")
        self.info_expiry.config(text="Expiry: -")
        set_badge(self.info_badge, "")

    # --- actions ---
    def log_member(self):
        m = self.selected
        if m is None:
            messagebox.showinfo("Log Attendance", "Search and select a member first.")
            return
        status = self.data.status_of(m)
        if status in ("Expired", "Inactive"):
            # FR-05: warn the staff when a member's plan is not valid
            if not messagebox.askyesno(
                    "Membership " + status,
                    "%s's membership is %s.\nPlease ask the member to renew.\n\nLog this visit anyway?"
                    % (m.name, status.upper())):
                return
        elif status == "Expiring Soon":
            messagebox.showinfo("Expiring Soon", "%s's membership expires in %d day(s)."
                                % (m.name, self.data.days_left(m)))
        earlier = self.data.checked_in_today(m.id)
        if earlier and not messagebox.askyesno("Already checked in", "%s already checked in today at %s.\n\n"
                                               "Log another visit?" % (m.name, earlier.time_in)):
            return
        record = self.data.log_member_attendance(m)
        self.flash("Attendance logged for %s at %s" % (m.name, record.time_in))
        self.clear_member()
        self.reload()

    def save_daily(self):
        try:
            record = self.data.log_daily_session(self.d_name.get(), self.d_contact.get(), self.d_amount.get(),
                                                 self.d_method.get(), self.d_ref.get())
        except ValueError as error:
            messagebox.showwarning("Daily Sessioner", str(error))
            return
        self.flash("Daily session saved for %s" % record.visitor)
        self.clear_daily()
        self.reload()

    def clear_daily(self):
        for var in (self.d_name, self.d_contact, self.d_amount, self.d_ref):
            var.set("")
        self.d_method.set("Cash")

    def reload(self):
        d = self.data
        todays = [a for a in d.attendance if a.date == d.today()]
        self.total_label.config(text="Total today: %d" % len(todays))
        text = self.filter_var.get().strip().lower()
        rows = []
        for number, a in enumerate(todays, start=1):
            row = [number, a.time_in, d.attendance_name(a), a.type, a.status, a.by]
            if not text or any(text in str(cell).lower() for cell in row):
                rows.append(row)
        fill_table(self.tree, rows, status_col=4)
        if self.selected:
            self.show_member_info()


# ------------------------------------------------------------- MEMBER RECORDS
class MemberRecordsPage(Page):
    def __init__(self, parent, app):
        super().__init__(parent, app, "Member Records")
        self.page_number = 1
        self.selected_id = None

        # ---- toolbar: search + filters + Add Member
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", pady=(0, 8))
        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar(value="All")
        self.plan_var = tk.StringVar(value="All")
        make_label(bar, "Search ", color=GRAY, bg=BG).pack(side="left")
        make_entry(bar, self.search_var, 28).pack(side="left", ipady=4)
        make_label(bar, "   Status ", color=GRAY, bg=BG).pack(side="left")
        make_combo(bar, self.status_var, ["All", "Active", "Expiring Soon", "Expired", "Inactive"], 14).pack(side="left", ipady=2)
        make_label(bar, "   Plan ", color=GRAY, bg=BG).pack(side="left")
        make_combo(bar, self.plan_var, ["All"] + list(PLANS.keys()), 11).pack(side="left", ipady=2)
        make_button(bar, "Add Member", lambda: app.add_member(self.reload)).pack(side="right")
        for var in (self.search_var, self.status_var, self.plan_var):
            var.trace_add("write", lambda *a: self.filters_changed())

        # ---- two columns: table (left) and detail panel (right)
        columns = tk.Frame(self, bg=BG)
        columns.pack(fill="both", expand=True)
        columns.columnconfigure(0, weight=1)
        columns.rowconfigure(0, weight=1)

        left = make_card(columns)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        frame, self.tree = make_table(
            left, ["Member ID", "Name", "Contact Number", "Plan", "Start Date", "Expiry Date", "Status"],
            [68, 112, 106, 64, 84, 84, 88], height=9)
        frame.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        actions = tk.Frame(left, bg=WHITE)
        actions.pack(fill="x", padx=10, pady=(4, 4))
        make_button(actions, "View", self.view_selected, "outline").pack(side="left")
        make_button(actions, "Edit", self.edit_selected, "outline").pack(side="left", padx=6)
        make_button(actions, "Renew", self.renew_selected, "outline").pack(side="left")
        self.toggle_btn = make_button(actions, "Deactivate", self.toggle_selected, "outline")
        self.toggle_btn.pack(side="left", padx=6)
        self.count_label = make_label(actions, "", color=GRAY)
        self.count_label.pack(side="right")
        self.pager = tk.Frame(left, bg=WHITE)
        self.pager.pack(pady=(2, 10))

        self.build_detail_panel(columns)
        self.reload()

    # --- right-hand detail panel
    def build_detail_panel(self, parent):
        panel = make_card(parent)
        panel.grid(row=0, column=1, sticky="nsew")
        panel.config(width=400)
        panel.grid_propagate(False)
        self.placeholder = make_label(panel, "Select a member\nto see the full profile,\npayment history and\nattendance history.",
                                      color=GRAY)
        self.placeholder.pack(expand=True)
        self.detail = tk.Frame(panel, bg=WHITE)
        make_photo_placeholder(self.detail, 150, 90).pack(pady=(12, 6))
        self.d_name = make_label(self.detail, "", True, size=14)
        self.d_name.pack(anchor="w", padx=14)
        self.d_id = make_label(self.detail, "", color=GRAY)
        self.d_id.pack(anchor="w", padx=14, pady=(0, 6))
        grid = tk.Frame(self.detail, bg=WHITE)
        grid.pack(fill="x", padx=14)
        self.d_values = {}
        for i, label in enumerate(["Contact Number:", "Address:", "Plan:", "Expiry Date:", "Status:"]):
            make_label(grid, label, color=GRAY).grid(row=i, column=0, sticky="nw", pady=1)
            if label == "Status:":
                widget = make_badge(grid, "")
            else:
                widget = make_label(grid, "")
                widget.config(wraplength=170, justify="left")
            widget.grid(row=i, column=1, sticky="w", padx=(10, 0), pady=1)
            self.d_values[label] = widget
        notebook = ttk.Notebook(self.detail)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        pay_tab = tk.Frame(notebook, bg=WHITE)
        att_tab = tk.Frame(notebook, bg=WHITE)
        notebook.add(pay_tab, text="Payment History")
        notebook.add(att_tab, text="Attendance History")
        make_button(pay_tab, "Record Payment", self.renew_selected).pack(anchor="w", pady=6, padx=4)
        frame, self.pay_tree = make_table(pay_tab, ["Date", "Amount", "Method", "Ref. No.", "By"],
                                          [84, 74, 76, 62, 44], height=5)
        frame.pack(fill="both", expand=True)
        frame, self.att_tree = make_table(att_tab, ["Date", "Time In", "Status at Entry"], [90, 80, 110], height=6)
        frame.pack(fill="both", expand=True, pady=(6, 0))

    def show_detail(self):
        m = self.data.find_member(self.selected_id) if self.selected_id else None
        if m is None:
            self.detail.pack_forget()
            self.placeholder.pack(expand=True)
            return
        d = self.data
        self.placeholder.pack_forget()
        self.detail.pack(fill="both", expand=True)
        self.d_name.config(text=m.name)
        self.d_id.config(text="Member ID: " + m.id)
        self.d_values["Contact Number:"].config(text=m.contact)
        self.d_values["Address:"].config(text=m.address or "-")
        self.d_values["Plan:"].config(text=m.plan)
        self.d_values["Expiry Date:"].config(text=pretty(m.expiry))
        set_badge(self.d_values["Status:"], d.status_of(m))
        pays = sorted([p for p in d.payments if p.member_id == m.id], key=lambda p: (p.date, p.id), reverse=True)
        fill_table(self.pay_tree, [[pretty(p.date), money(p.amount), p.method, p.ref or "-", p.by] for p in pays])
        atts = sorted([a for a in d.attendance if a.member_id == m.id], key=lambda a: (a.date, a.id), reverse=True)
        fill_table(self.att_tree, [[pretty(a.date), a.time_in, a.status] for a in atts], status_col=2)
        self.toggle_btn.config(text="Reactivate" if not m.active else "Deactivate")

    # --- filtering, paging, table
    def filtered(self):
        d = self.data
        members = d.search_members(self.search_var.get())
        if self.status_var.get() != "All":
            members = [m for m in members if d.status_of(m) == self.status_var.get()]
        if self.plan_var.get() != "All":
            members = [m for m in members if m.plan == self.plan_var.get()]
        return sorted(members, key=lambda m: m.id)

    def filters_changed(self):
        self.page_number = 1
        self.reload()

    def reload(self):
        d = self.data
        members = self.filtered()
        pages = max(1, -(-len(members) // PAGE_SIZE))      # ceiling division
        self.page_number = min(self.page_number, pages)
        start = (self.page_number - 1) * PAGE_SIZE
        shown = members[start:start + PAGE_SIZE]
        fill_table(self.tree, [[m.id, m.name, m.contact, m.plan, pretty(m.start), pretty(m.expiry),
                                d.status_of(m)] for m in shown], status_col=6, iids=[m.id for m in shown])
        self.count_label.config(text="%d member(s)" % len(members))
        if self.selected_id and self.tree.exists(self.selected_id):
            self.tree.selection_set(self.selected_id)
        self.show_detail()
        self.build_pager(pages)

    def build_pager(self, pages):
        for child in self.pager.winfo_children():
            child.destroy()
        def go(n):
            self.page_number = n
            self.reload()
        prev_btn = make_button(self.pager, "Previous", lambda: go(self.page_number - 1), "outline")
        prev_btn.pack(side="left", padx=2)
        first = max(1, min(self.page_number - 2, pages - 4))
        for n in range(first, min(pages, first + 4) + 1):
            kind = "primary" if n == self.page_number else "outline"
            make_button(self.pager, str(n), lambda n=n: go(n), kind, width=3).pack(side="left", padx=2)
        next_btn = make_button(self.pager, "Next", lambda: go(self.page_number + 1), "outline")
        next_btn.pack(side="left", padx=2)
        if self.page_number <= 1:
            prev_btn.config(state="disabled")
        if self.page_number >= pages:
            next_btn.config(state="disabled")

    # --- row actions
    def on_select(self, event=None):
        selection = self.tree.selection()
        if selection:
            self.selected_id = selection[0]
            self.show_detail()

    def current_member(self):
        m = self.data.find_member(self.selected_id) if self.selected_id else None
        if m is None:
            messagebox.showinfo("Member Records", "Click a member in the table first.")
        return m

    def view_selected(self):
        if self.current_member():
            self.show_detail()

    def renew_selected(self):
        m = self.current_member()
        if m:
            PaymentDialog(self.app, m, self.reload)

    def edit_selected(self):
        m = self.current_member()
        if not m:
            return
        if not self.data.is_admin():
            messagebox.showwarning("Access denied", "Only the Admin can edit member details.")
            return

        def save(v):
            self.data.edit_member(m, v["contact"], v["address"], v["em_name"], v["em_contact"])
            self.reload()
            self.flash("Member updated")
        FormDialog(self.app, "Edit Member - %s" % m.name, [
            ("contact", "Contact number*", "text", m.contact, None),
            ("address", "Address", "text", m.address, None),
            ("em_name", "Emergency contact name*", "text", m.em_name, None),
            ("em_contact", "Emergency contact no.*", "text", m.em_contact, None),
        ], save, intro="Editing %s (%s). The name and plan cannot be changed here." % (m.name, m.id))

    def toggle_selected(self):
        m = self.current_member()
        if not m:
            return
        if not self.data.is_admin():
            messagebox.showwarning("Access denied", "Only the Admin can deactivate or reactivate members.")
            return
        action = "reactivate" if not m.active else "deactivate"
        if messagebox.askyesno("Confirm", "Do you want to %s %s?" % (action, m.name)):
            self.data.set_member_active(m, not m.active)
            self.reload()
            self.flash("%s %sd" % (m.name, action))


# -------------------------------------------------------------------- REPORTS
class ReportsPage(Page):
    def __init__(self, parent, app):
        super().__init__(parent, app, "Reports")
        self.report = None              # the report currently on screen (used by the export buttons)

        # ---- filter bar
        bar = make_card(self)
        bar.pack(fill="x")
        row = tk.Frame(bar, bg=WHITE)
        row.pack(fill="x", padx=14, pady=10)
        today = self.data.today()
        self.type_var = tk.StringVar(value="Payments")
        self.from_var = tk.StringVar(value=iso(today.replace(day=1)))
        self.to_var = tk.StringVar(value=iso(today))
        self.member_var = tk.StringVar()
        fields = [("Report Type", None), ("Date From (YYYY-MM-DD)", None), ("Date To (YYYY-MM-DD)", None),
                  ("Member (Optional)", None)]
        for i, (text, _) in enumerate(fields):
            make_label(row, text, color=GRAY).grid(row=0, column=i, sticky="w", padx=(0 if i == 0 else 10, 0))
        self.type_box = make_combo(row, self.type_var, ["Payments", "Attendance", "Membership Status"], 18)
        self.type_box.grid(row=1, column=0, ipady=3)
        self.type_box.bind("<<ComboboxSelected>>", lambda e: self.type_changed())
        self.from_entry = make_entry(row, self.from_var, 14)
        self.from_entry.grid(row=1, column=1, padx=(10, 0), ipady=4)
        self.to_entry = make_entry(row, self.to_var, 14)
        self.to_entry.grid(row=1, column=2, padx=(10, 0), ipady=4)
        make_entry(row, self.member_var, 18).grid(row=1, column=3, padx=(10, 0), ipady=4)
        make_button(row, "Generate Report", self.generate).grid(row=1, column=4, padx=(14, 0))
        make_button(row, "Reset", self.reset, "outline").grid(row=1, column=5, padx=(6, 0))

        # ---- three summary cards
        cards = tk.Frame(self, bg=BG)
        cards.pack(fill="x", pady=10)
        self.cards = []
        for i in range(3):
            cards.columnconfigure(i, weight=1, uniform="rep")
            card = StatCard(cards, "-")
            card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0 if i == 2 else 6))
            self.cards.append(card)

        # ---- export buttons + result table
        export = tk.Frame(self, bg=BG)
        export.pack(fill="x")
        self.title_label = make_label(export, "", True, bg=BG, size=11)
        self.title_label.pack(side="left")
        make_button(export, "Export to CSV", lambda: self.export("csv"), "outline").pack(side="right")
        make_button(export, "Export to PDF", lambda: self.export("pdf"), "outline").pack(side="right", padx=6)
        card = make_card(self)
        card.pack(fill="both", expand=True, pady=(6, 0))
        frame, self.tree = make_table(card, ["Date", "Member ID", "Name", "Amount", "Method", "Reference No.", "Encoded By"],
                                      [100, 90, 160, 100, 100, 120, 100], height=10)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.generate(log=False)

    def type_changed(self):
        # The membership status report is a snapshot of today, so dates do not apply.
        state = "disabled" if self.type_var.get() == "Membership Status" else "normal"
        self.from_entry.config(state=state)
        self.to_entry.config(state=state)

    def reset(self):
        today = self.data.today()
        self.type_var.set("Payments")
        self.from_var.set(iso(today.replace(day=1)))
        self.to_var.set(iso(today))
        self.member_var.set("")
        self.type_changed()
        self.generate()

    def generate(self, log=True):
        """Build the report and show it. log=False when the page first opens,
        so the audit log only records reports the user really asked for."""
        kind = self.type_var.get()
        try:
            if kind == "Membership Status":
                report = self.data.report_membership(self.member_var.get())
            else:
                d_from, d_to = parse_date(self.from_var.get()), parse_date(self.to_var.get())
                if d_from is None or d_to is None:
                    raise ValueError("Dates must be in YYYY-MM-DD format, for example 2026-10-04.")
                if d_from > d_to:
                    raise ValueError("'Date From' must not be later than 'Date To'.")
                if kind == "Payments":
                    report = self.data.report_payments(d_from, d_to, self.member_var.get())
                else:
                    report = self.data.report_attendance(d_from, d_to, self.member_var.get())
        except (ValueError, PermissionError) as error:
            messagebox.showwarning("Reports", str(error))
            return
        self.report = report
        widths = [max(80, int(900 / len(report["columns"])))] * len(report["columns"])
        set_table_columns(self.tree, report["columns"], widths)
        status_col = report["columns"].index("Status") if "Status" in report["columns"] else None
        fill_table(self.tree, report["rows"], status_col=status_col, total_row=report["total_row"])
        for card, (label, value) in zip(self.cards, report["summary"]):
            card.set(label, value)
        self.title_label.config(text=report["title"])
        if log:
            self.data.audit("Generate Report", report["title"])
            self.data.save_all()

    def export(self, kind):
        if not self.report:
            return
        r = self.report
        base = r["title"].split(" (")[0].replace(" ", "_").lower()
        path = filedialog.asksaveasfilename(
            parent=self.app, title="Export report", initialdir=BASE_DIR, initialfile=base + "." + kind,
            defaultextension="." + kind,
            filetypes=[("CSV file", "*.csv")] if kind == "csv" else [("PDF file", "*.pdf")])
        if not path:
            return
        rows = list(r["rows"]) + ([r["total_row"]] if r["total_row"] else [])
        try:
            if kind == "csv":
                with open(path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(r["columns"])
                    writer.writerows(rows)
            else:
                info = ["Generated: %s by %s" % (self.data.now_stamp(), self.data.current_user.full_name),
                        "   ".join("%s: %s" % (a, b) for a, b in r["summary"])]
                write_simple_pdf(path, "%s - %s" % (APP_NAME, r["title"]), info, r["columns"], rows)
        except OSError as error:
            messagebox.showerror("Export failed", "Could not save the file:\n%s" % error)
            return
        self.data.audit("Export Report", "%s -> %s" % (r["title"], os.path.basename(path)))
        self.data.save_all()
        messagebox.showinfo("Export complete", "Saved to:\n%s" % path)


# ----------------------------------------------------------------- USER PROFILE
class UserProfilePage(Page):
    def __init__(self, parent, app):
        super().__init__(parent, app, "User Profile")
        u = self.data.current_user

        # ---- Account Information
        info = make_card(self, "Account Information")
        info.pack(fill="x")
        grid = tk.Frame(info, bg=WHITE)
        grid.pack(fill="x", padx=14, pady=(0, 12))
        grid.columnconfigure(0, weight=1, uniform="p")
        grid.columnconfigure(1, weight=1, uniform="p")
        self.name_var, self.contact_var = tk.StringVar(value=u.full_name), tk.StringVar(value=u.contact)
        self.email_var, self.user_var = tk.StringVar(value=u.email), tk.StringVar(value=u.username)
        make_label(grid, "Full Name", color=GRAY).grid(row=0, column=0, sticky="w")
        make_entry(grid, self.name_var, 30).grid(row=1, column=0, sticky="ew", padx=(0, 10), ipady=4)
        make_label(grid, "Contact Number", color=GRAY).grid(row=0, column=1, sticky="w")
        make_entry(grid, self.contact_var, 30).grid(row=1, column=1, sticky="ew", ipady=4)
        make_label(grid, "Username", color=GRAY).grid(row=2, column=0, sticky="w", pady=(8, 0))
        make_entry(grid, self.user_var, 30, readonly=True).grid(row=3, column=0, sticky="ew", padx=(0, 10), ipady=4)
        make_label(grid, "Email", color=GRAY).grid(row=2, column=1, sticky="w", pady=(8, 0))
        make_entry(grid, self.email_var, 30).grid(row=3, column=1, sticky="ew", ipady=4)
        make_label(grid, "Role: " + u.role, True).grid(row=4, column=0, sticky="w", pady=(10, 0))
        make_button(grid, "Save Changes", self.save_profile).grid(row=4, column=1, sticky="e", pady=(10, 0))

        # ---- Change Password
        pw = make_card(self, "Change Password")
        pw.pack(fill="x", pady=10)
        form = tk.Frame(pw, bg=WHITE)
        form.pack(fill="x", padx=14, pady=(0, 12))
        self.cur_var, self.new_var, self.conf_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.pw_entries = []
        for i, (text, var) in enumerate([("Current Password", self.cur_var), ("New Password", self.new_var),
                                         ("Confirm New Password", self.conf_var)]):
            make_label(form, text, color=GRAY).grid(row=0, column=i, sticky="w", padx=(0 if i == 0 else 10, 0))
            entry = make_entry(form, var, 26, show="*")
            entry.grid(row=1, column=i, sticky="ew", padx=(0 if i == 0 else 10, 0), ipady=4)
            self.pw_entries.append(entry)
            form.columnconfigure(i, weight=1, uniform="pw")
        make_label(form, "At least 8 characters with a number", color=GRAY).grid(row=2, column=1, sticky="w", padx=(10, 0))
        self.show_var = tk.BooleanVar(value=False)
        tk.Checkbutton(form, text="Show passwords", variable=self.show_var, command=self.toggle_show, bg=WHITE,
                       font=FONT, activebackground=WHITE).grid(row=2, column=0, sticky="w")
        buttons = tk.Frame(form, bg=WHITE)
        buttons.grid(row=2, column=2, sticky="e", pady=(6, 0))
        make_button(buttons, "Update Password", self.update_password).pack(side="left")
        make_button(buttons, "Cancel", self.clear_passwords, "outline").pack(side="left", padx=6)

        # ---- Activity Log
        log = make_card(self, "Activity Log")
        log.pack(fill="both", expand=True)
        frame, self.tree = make_table(log, ["Date and Time", "User", "Action", "Details"], [170, 100, 150, 380], height=6)
        frame.pack(fill="both", expand=True, padx=14)
        bar = tk.Frame(log, bg=WHITE)
        bar.pack(fill="x", padx=14, pady=6)
        make_link(bar, "View Full Log", self.view_full_log).pack(side="left")
        self.reload()

    def toggle_show(self):
        for entry in self.pw_entries:
            entry.config(show="" if self.show_var.get() else "*")

    def clear_passwords(self):
        for var in (self.cur_var, self.new_var, self.conf_var):
            var.set("")

    def save_profile(self):
        try:
            self.data.update_profile(self.name_var.get(), self.contact_var.get(), self.email_var.get())
        except ValueError as error:
            messagebox.showwarning("User Profile", str(error))
            return
        self.app.refresh_topbar()
        self.reload()
        self.flash("Profile saved")

    def update_password(self):
        try:
            self.data.change_password(self.cur_var.get(), self.new_var.get(), self.conf_var.get())
        except ValueError as error:
            messagebox.showwarning("Change Password", str(error))
            return
        self.clear_passwords()
        self.reload()
        self.flash("Password updated")

    def view_full_log(self):
        if self.data.is_admin():
            self.app.navigate("Audit Logs")
        else:
            mine = self.data.user_activity(self.data.current_user.username, limit=500)
            window = tk.Toplevel(self.app, bg=WHITE)
            window.title("My Full Activity Log")
            frame, tree = make_table(window, ["Date and Time", "Action", "Details"], [170, 150, 380], height=18)
            frame.pack(fill="both", expand=True, padx=10, pady=10)
            fill_table(tree, [[a.stamp, a.action, a.details] for a in mine])

    def reload(self):
        mine = self.data.user_activity(self.data.current_user.username)
        fill_table(self.tree, [[a.stamp, a.user, a.action, a.details] for a in mine])


# ---------------------------------------------------------------- MANAGE USERS
class ManageUsersPage(Page):
    def __init__(self, parent, app):
        super().__init__(parent, app, "Manage Users")
        make_button(self.header_right, "Create Staff Account", self.create_staff).pack(side="left", padx=4)
        make_button(self.header_right, "Activate / Deactivate", self.toggle, "outline").pack(side="left", padx=4)
        make_button(self.header_right, "Reset Password", self.reset_password, "outline").pack(side="left", padx=4)
        card = make_card(self)
        card.pack(fill="both", expand=True)
        frame, self.tree = make_table(card, ["ID", "Full Name", "Username", "Role", "Status"], [50, 220, 150, 100, 100], height=12)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.reload()

    def reload(self):
        rows = [[u.id, u.full_name, u.username, u.role, "Active" if u.active else "Inactive"] for u in self.data.users]
        fill_table(self.tree, rows, status_col=4, iids=[str(u.id) for u in self.data.users])

    def selected_user(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Manage Users", "Click a user in the table first.")
            return None
        return next(u for u in self.data.users if str(u.id) == selection[0])

    def create_staff(self):
        def save(v):
            self.data.create_staff(v["name"], v["username"], v["password"])
            self.reload()
            self.flash("Staff account created")
        FormDialog(self.app, "Create Staff Account", [
            ("name", "Full name*", "text", "", None),
            ("username", "Username*", "text", "", None),
            ("password", "Temporary password*", "password", "", None),
        ], save, "Create", intro="Password: at least 8 characters with a number.")

    def toggle(self):
        user = self.selected_user()
        if user:
            try:
                self.data.toggle_user_active(user)
            except ValueError as error:
                messagebox.showwarning("Manage Users", str(error))
                return
            self.reload()

    def reset_password(self):
        user = self.selected_user()
        if not user:
            return

        def save(v):
            self.data.reset_password(user, v["password"])
            self.flash("Password reset for " + user.username)
        FormDialog(self.app, "Reset Password - %s" % user.username, [
            ("password", "New temporary password*", "password", "", None),
        ], save, "Reset", intro="Password: at least 8 characters with a number.")


# ------------------------------------------------------------------ AUDIT LOGS
class AuditLogsPage(Page):
    def __init__(self, parent, app):
        super().__init__(parent, app, "Audit Logs")
        self.filter_var = tk.StringVar()
        make_entry(self.header_right, self.filter_var, 28).pack(side="right", ipady=4)
        make_label(self.header_right, "Filter / Search ", color=GRAY, bg=BG).pack(side="right")
        self.filter_var.trace_add("write", lambda *a: self.reload())
        card = make_card(self)
        card.pack(fill="both", expand=True)
        frame, self.tree = make_table(card, ["Date and Time", "User", "Action", "Details"], [170, 110, 160, 420], height=14)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.count = make_label(card, "", color=GRAY)
        self.count.pack(anchor="w", padx=14, pady=(0, 8))
        self.reload()

    def reload(self):
        text = self.filter_var.get().strip().lower()
        entries = [a for a in reversed(self.data.audit_log)
                   if not text or text in (a.user + a.action + a.details + a.stamp).lower()]
        fill_table(self.tree, [[a.stamp, a.user, a.action, a.details] for a in entries[:500]])
        self.count.config(text="Showing %d of %d entries (newest first)" % (min(len(entries), 500), len(self.data.audit_log)))


# =============================================================================
# 8. THE LOGIN SCREEN AND THE MAIN WINDOW
# =============================================================================
class LoginScreen(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app
        self.failed = 0
        # outer frame = 1 pixel light-gray border, inner frame = the white card
        outline = tk.Frame(self, bg=BORDER, padx=1, pady=1)
        outline.place(relx=0.5, rely=0.46, anchor="center")
        card = tk.Frame(outline, bg=WHITE, padx=36, pady=26)
        card.pack()
        logo = make_photo_placeholder(card, 56, 56)
        logo.pack(pady=(0, 8))
        tk.Label(card, text=APP_NAME, font=("Segoe UI", 22, "bold"), fg=NAVY, bg=WHITE).pack()
        tk.Label(card, text=APP_SUBTITLE, font=FONT_SMALL, fg=GRAY, bg=WHITE).pack(pady=(0, 14))
        self.user_var, self.pass_var = tk.StringVar(), tk.StringVar()
        make_label(card, "Username", color=GRAY).pack(anchor="w")
        self.user_entry = make_entry(card, self.user_var, 38)
        self.user_entry.pack(fill="x", ipady=5, pady=(2, 8))
        make_label(card, "Password", color=GRAY).pack(anchor="w")
        pw_row = tk.Frame(card, bg=WHITE)
        pw_row.pack(fill="x", pady=(2, 0))
        self.pass_entry = make_entry(pw_row, self.pass_var, 32, show="*")
        self.pass_entry.pack(side="left", fill="x", expand=True, ipady=5)
        self.eye = make_link(pw_row, "Show", self.toggle_password)
        self.eye.pack(side="left", padx=(6, 0))
        self.error = tk.Label(card, text="", font=FONT_SMALL, fg=RED, bg=WHITE, wraplength=300, justify="left")
        self.error.pack(anchor="w", pady=(6, 6))
        self.login_btn = make_button(card, "Login", self.try_login)
        self.login_btn.pack(fill="x", ipady=3)
        make_link(card, "Forgot Password? Contact the Admin", self.forgot).pack(pady=(10, 0))
        tk.Label(self, text="System Version " + APP_VERSION, font=FONT_SMALL, fg=GRAY, bg=BG).place(
            relx=0.5, rely=0.93, anchor="center")
        self.user_entry.focus_set()
        for entry in (self.user_entry, self.pass_entry):
            entry.bind("<Return>", lambda e: self.try_login())

    def toggle_password(self):
        showing = self.pass_entry.cget("show") == ""
        self.pass_entry.config(show="*" if showing else "")
        self.eye.config(text="Show" if showing else "Hide")

    def forgot(self):
        messagebox.showinfo("Forgot Password", "Please contact the gym Admin to reset your password.")

    def try_login(self):
        if str(self.login_btn.cget("state")) == "disabled":
            return
        try:
            self.app.data.login(self.user_var.get(), self.pass_var.get())
        except ValueError as error:
            self.failed += 1
            self.error.config(text=str(error))
            self.pass_var.set("")
            if self.failed >= MAX_LOGIN_ATTEMPTS:        # too many tries: lock for a short time
                self.failed = 0
                self.lock(LOCKOUT_SECONDS)
            return
        self.app.show_main()

    def lock(self, seconds):
        """Disable the Login button and count down, so passwords cannot be guessed quickly."""
        if seconds <= 0:
            self.login_btn.config(state="normal", text="Login")
            self.error.config(text="")
            return
        self.login_btn.config(state="disabled", text="Locked - try again in %d s" % seconds)
        self.error.config(text="Too many failed attempts.")
        self.after(1000, lambda: self.lock(seconds - 1))


class App(tk.Tk):
    # (sidebar text, page class, admin only?)
    PAGES = [
        ("Dashboard", DashboardPage, False),
        ("Log Attendance", LogAttendancePage, False),
        ("Member Records", MemberRecordsPage, False),
        ("Reports", ReportsPage, True),
        ("User Profile", UserProfilePage, False),
        ("Manage Users", ManageUsersPage, True),
        ("Audit Logs", AuditLogsPage, True),
    ]

    def __init__(self):
        super().__init__()
        self.title("%s - %s" % (APP_NAME, APP_SUBTITLE))
        self.data = GymData()
        width = min(1340, self.winfo_screenwidth() - 40)
        height = min(780, self.winfo_screenheight() - 90)
        self.geometry("%dx%d+30+20" % (width, height))
        self.minsize(1080, 640)
        self.configure(bg=BG)
        self.setup_styles()
        self.page = None
        self.page_name = None
        self.nav_buttons = {}
        self.last_activity = time.time()
        # any key press / click / mouse move counts as "activity" (for the 15-minute timeout)
        for event in ("<Key>", "<Button>", "<Motion>"):
            self.bind_all(event, self.touch, add="+")
        self.after(10000, self.check_timeout)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.show_login()

    def setup_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")          # 'clam' looks the same on every computer
        style.configure("Treeview", rowheight=26, font=FONT_SMALL, background=WHITE, fieldbackground=WHITE,
                        foreground=DARK, borderwidth=0)
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background=HEAD_BG, foreground=NAVY,
                        relief="flat", padding=(6, 5))
        style.map("Treeview", background=[("selected", "#CFE0F7")], foreground=[("selected", "#000000")])
        style.map("Treeview.Heading", background=[("active", HEAD_BG)])
        style.configure("TNotebook", background=WHITE, borderwidth=0)
        style.configure("TNotebook.Tab", font=FONT, padding=(10, 5))

    # ------------------------------------------------------------- screens
    def clear_window(self):
        for child in self.winfo_children():
            child.destroy()
        self.page = None
        self.nav_buttons = {}

    def show_login(self):
        self.clear_window()
        LoginScreen(self, self).pack(fill="both", expand=True)

    def show_main(self):
        """Builds the layout from the wireframes: top bar, sidebar, content area."""
        self.clear_window()
        self.last_activity = time.time()
        # ---- top bar
        top = tk.Frame(self, bg=WHITE, highlightthickness=1, highlightbackground=BORDER)
        top.pack(fill="x")
        tk.Label(top, text=APP_NAME, font=("Segoe UI", 15, "bold"), fg=NAVY, bg=WHITE).pack(side="left", padx=18, pady=10)
        make_button(top, "Logout", self.logout, "outline").pack(side="right", padx=18)
        self.user_label = tk.Label(top, font=FONT, fg=DARK, bg=WHITE)
        self.user_label.pack(side="right", padx=8)
        self.demo_label = tk.Label(top, font=FONT_BOLD, fg=RED, bg=WHITE)
        if self.data.is_admin():
            make_link(top, "Demo Date", self.demo_date).pack(side="right", padx=4)
        self.demo_label.pack(side="right", padx=4)
        self.refresh_topbar()
        # ---- body = sidebar + content
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)
        sidebar = tk.Frame(body, bg=NAVY, width=200)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Frame(sidebar, bg=NAVY, height=10).pack()
        for name, page_class, admin_only in self.PAGES:
            if admin_only and not self.data.is_admin():
                continue                # Staff never see Admin-only pages
            btn = tk.Button(sidebar, text=name, anchor="w", font=FONT, fg=WHITE, bg=NAVY, relief="flat", bd=0,
                            padx=18, pady=9, activebackground=BLUE, activeforeground=WHITE, cursor="hand2",
                            highlightthickness=0, command=lambda n=name: self.navigate(n))
            btn.pack(fill="x")
            self.nav_buttons[name] = btn
        self.content = tk.Frame(body, bg=BG, padx=20, pady=14)
        self.content.pack(side="left", fill="both", expand=True)
        self.navigate("Dashboard")

    def refresh_topbar(self):
        u = self.data.current_user
        self.user_label.config(text="%s - %s" % (u.role, u.full_name))
        offset = self.data.date_offset
        self.demo_label.config(text="" if offset == 0 else "DEMO DATE: " + pretty(self.data.today()))

    def navigate(self, name):
        """Show one page: destroy the old one, build the new one, highlight the sidebar item."""
        for page_name, page_class, admin_only in self.PAGES:
            if page_name == name:
                if admin_only and not self.data.is_admin():
                    messagebox.showwarning("Access denied", "This page is for the Admin only.")
                    return
                if self.page:
                    self.page.destroy()
                self.page = page_class(self.content, self)
                self.page.pack(fill="both", expand=True)
                self.page_name = name
        for btn_name, btn in self.nav_buttons.items():
            btn.config(bg=BLUE if btn_name == name else NAVY)

    def reload_page(self):
        if self.page:
            self.page.reload()

    # ------------------------------------------------------- shared actions
    def add_member(self, after_done=None):
        """Add Member form. Used by the Dashboard and Member Records pages."""
        def save(v):
            member = self.data.register_member(v["name"], v["contact"], v["address"], v["birthdate"],
                                               v["gender"], v["em_name"], v["em_contact"])
            self.after(150, lambda: self.after_register(member, after_done))
        FormDialog(self, "Register New Member", [
            ("name", "Full name*", "text", "", None),
            ("contact", "Contact number*", "text", "", None),
            ("address", "Address", "text", "", None),
            ("birthdate", "Birthdate (YYYY-MM-DD)", "text", "", None),
            ("gender", "Gender", "combo", "", ["", "Male", "Female", "Prefer not to say"]),
            ("em_name", "Emergency contact name*", "text", "", None),
            ("em_contact", "Emergency contact no.*", "text", "", None),
        ], save, "Register", intro="Fields marked * are required.")

    def after_register(self, member, after_done):
        if after_done:
            after_done()
        if messagebox.askyesno("Member registered",
                               "%s was registered with ID %s.\n\nRecord the membership payment now?"
                               % (member.name, member.id)):
            PaymentDialog(self, member, after_done)
        else:
            messagebox.showinfo("No payment yet", "Status stays 'Expired' until a payment is recorded.")

    def demo_date(self):
        """Admin demo tool: pretend today is later/earlier to show expiry detection."""
        def save(v):
            try:
                days = int(v["days"])
            except ValueError:
                raise ValueError("Enter a whole number, for example 10, -10 or 0.")
            if not -3650 <= days <= 3650:
                raise ValueError("Enter a number between -3650 and 3650.")
            self.data.set_demo_offset(days)
            self.refresh_topbar()
            self.reload_page()
        FormDialog(self, "Demo Date", [("days", "Days from real today", "text", str(self.data.date_offset), None)],
                   save, "Apply",
                   intro="Pretend the date is that many days from today (use 0 to go back to the real date). "
                         "Useful to show members becoming Expiring Soon / Expired.")

    # ------------------------------------------------- logout and time-out
    def logout(self):
        self.data.logout()
        self.show_login()

    def touch(self, event=None):
        self.last_activity = time.time()

    def check_timeout(self):
        """Runs every 10 seconds. Logs out after 15 minutes without activity."""
        if self.data.current_user and time.time() - self.last_activity > SESSION_TIMEOUT_SECONDS:
            self.data.logout("Session timed out after inactivity")
            self.show_login()
            messagebox.showinfo("Session timed out", "You were logged out after 15 minutes of inactivity.")
        self.after(10000, self.check_timeout)

    def on_close(self):
        self.data.save_all()
        self.destroy()


# =============================================================================
# PROGRAM START
# =============================================================================
if __name__ == "__main__":
    try:                                 # makes text sharp on high-resolution Windows screens
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    App().mainloop()