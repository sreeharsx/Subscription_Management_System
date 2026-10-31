# BrightLoop Subscription Management System
> Built with **Django + SQLite + Django Templates + Bootstrap 5** for an 8-hour hackathon.

---

## 1. System Overview

BrightLoop Subscription Management System is an end-to-end, enterprise-grade recurring billing and subscription engine. It guarantees financial consistency, billing idempotency, and role-based data isolation across the entire customer revenue lifecycle:

```
Product & Plan → Customer Profile → Quotation → Accepted Quotation → Subscription → Billing Engine → Invoice → Payment → Live Dashboard
```

---

## 2. Key Architecture & Business Rules Enforced

### A. Idempotent Billing Engine (Duplicate Invoice Prevention)
- **Problem**: Cron jobs, double-clicks, or repeated billing runs could issue duplicate invoices.
- **Solution**: Database-level `unique_together = [('subscription', 'billing_period_key')]` and atomic transactions with `get_or_create`.
- **Result**: Re-running billing for any billing period produces zero duplicate invoices.

### B. Accurate Financial Calculations (Decimal Arithmetic)
- **Problem**: IEEE 754 floating-point rounding errors lead to discrepancies in accounting.
- **Solution**: 100% pure Python `Decimal` and Django `DecimalField(max_digits=10, decimal_places=2)`.
- **Order of Calculations**:
  1. Base Plan Price
  2. Eligible Discount (`Percentage` or `Fixed`)
  3. Applicable Tax (`(Base - Discount) * Tax%`)
  4. Final Total (`Taxable + Tax`)

### C. Single Source of Truth & Pricing Snapshots
- Changing a plan's price in the catalogue does **not** alter existing quotations or historical invoices.
- Each quotation and subscription captures an immutable snapshot of base price, discount, and tax rate at creation time.

### D. Single-Subscription Enforcement
- Enforced via `OneToOneField(Quotation, related_name='subscription')`.
- Accepting an already-accepted quotation redirects safely to the existing subscription without generating duplicates.

### E. Row-Level Data Isolation (RBAC)
- Customers are strictly confined to their own quotations, subscriptions, and invoices.
- URL manipulation (e.g., changing `/billing/invoices/1/` to `/billing/invoices/2/`) returns a server-enforced `403 Forbidden`.

### F. Real-Time Dashboard Metrics
- **Collected Revenue** calculates the actual sum of `COMPLETED` payments, never issued invoices.
- **Outstanding Balance** accurately tracks unpaid or partially paid amounts (`total_amount - amount_paid`).
- **Overdue Invoices** tracks balances where `due_date < today`.

---

## 3. Technology Stack

- **Backend**: Python 3.13 + Django 6.1
- **Database**: SQLite with transactions, indexes, and unique constraints
- **Frontend**: Django Templates + Bootstrap 5.3 + Bootstrap Icons + Chart.js
- **Testing**: Django `TestCase` with `Client` test suite

---

## 4. Quickstart & Setup Guide

### 1. Prerequisites & Virtual Environment
```bash
python --version  # Python 3.10+
pip install -r requirements.txt
```

### 2. Run Database Migrations
```bash
python manage.py migrate
```

### 3. Seed Demo Data (Instant 1-Click Setup)
```bash
python manage.py seed_data
```

### 4. Run Automated Test Suite
```bash
python manage.py test
```

### 5. Launch Development Server
```bash
python manage.py runserver
```
Visit: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

---

## 5. Demo Accounts

| Role | Username | Password | Purpose |
|---|---|---|---|
| **Admin** | `admin` | `admin123` | Full administrative control, products, catalogue, billing |
| **Staff** | `staff` | `staff123` | CRM, quotation creation, billing run, payment recording |
| **Customer 1** | `acme` | `acme123` | Acme Technologies (active subscription, partial payment) |
| **Customer 2** | `globex` | `globex123` | Globex Logistics (sent quotation awaiting acceptance) |
| **Customer 3** | `initech` | `initech123` | Initech Innovations (draft quotation) |

---

## 6. End-to-End Demonstration Walkthrough

1. **Login as Staff (`staff` / `staff123`)**:
   - Navigate to **Products & Plans** → view existing catalogue (Starter, Enterprise, Growth).
   - Navigate to **Customers** → view Acme, Globex, Initech.
2. **Create Quotation**:
   - Go to **Quotations** → **New Quotation**.
   - Select Customer, Plan, Tax (GST 18%), and Discount (Festive 15%).
   - Click **Save Quotation** → view pricing breakdown with automatic discount and tax calculations.
3. **Accept Quotation & Generate Subscription**:
   - Click **Send to Customer**, then **Accept & Create Subscription**.
   - Notice the system automatically creates the `Subscription` with immutable snapshots.
4. **Run Billing Engine (Demonstrate Idempotency)**:
   - Click **Run Billing** from navigation or subscription page.
   - Run billing for today: Invoice is generated (e.g., `INV-00001-2026-10`).
   - Run billing a second time: Notice **0 invoices created**, **1 skipped** (duplicate prevention verified!).
5. **Record Partial & Final Payment**:
   - Open invoice → Click **Record Payment**.
   - Enter partial payment (e.g. ₹500) → Invoice status updates to `Partially Paid` and outstanding balance drops.
   - Enter remaining balance → Invoice status transitions to `Paid` with timestamp.
6. **Customer Portal & Data Isolation**:
   - Log out and log in as `acme` (`acme123`).
   - Customer sees only their own subscriptions and invoices.
   - Attempting to access another customer's invoice directly by URL returns `403 Forbidden`.
7. **Executive Dashboard**:
   - Log back into `admin` or `staff`.
   - Dashboard instantly visualizes total collected revenue (from payments), outstanding amounts, overdue balances, and 6-month revenue trends.
