# Synthetic account health data

**Account and ticket data in this folder is simulated.** It was generated with planted risk patterns so the customer health score can be validated against known outcomes. It does not describe real organizations or patients.

Scenario: a vendor of cloud-based cardiac imaging analysis software supports 400 customer accounts (hospital systems, community hospitals, imaging centers and cardiology practices) from **2025-07-01 to 2026-10-31**. The snapshot date ("today") is **2026-10-31**.

Regenerate with `python generate_health_data.py --seed 42`. The same seed always gives the same files.

## Files

| File | Rows | Use |
|---|---|---|
| `data/accounts.csv` | 400 | Account attributes. Safe to use for scoring. |
| `data/tickets.csv` | ~22,500 | Support tickets. Safe to use for scoring. |
| `truth/account_truth.csv` | 400 | **Hidden labels.** Use only to *evaluate* the score, never as an input to it. |

## accounts.csv

| Column | Description |
|---|---|
| account_id | `ACC-1001` … unique account key |
| account_name | Invented organization name |
| segment | Hospital system, Community hospital, Imaging center, Cardiology practice |
| region | US region |
| product_tier | Standard, Professional, Enterprise |
| seats | Licensed users; larger accounts open more tickets |
| contract_start_date | About 30% of accounts start during the window and show an onboarding ticket burst |
| annual_contract_value | USD, roughly seats × segment price |

## tickets.csv

| Column | Description |
|---|---|
| ticket_id | `TCK-100001` … unique, in creation order |
| account_id | Foreign key to accounts |
| created_at | Ticket opened |
| first_response_at | First agent response; blank if not yet responded by snapshot |
| resolved_at | Blank if still open at snapshot |
| status | Closed, Open, Pending customer |
| priority | Low, Medium, High, Critical |
| channel | Email, Phone, Portal, Chat |
| category | 9-category taxonomy (Login & access, Image upload & transfer, Analysis report delay, Report content question, EHR/PACS integration, Billing & invoicing, Training request, Feature request, Account & contract) |
| subject | Short templated subject line |
| satisfaction_rating | 1–5 post-resolution survey; about 42% of closed tickets have a response, the rest are blank |

Repeat contacts aren't flagged; derive them yourself (same account and category within 30 days).

## account_truth.csv (hidden)

| Column | Description |
|---|---|
| true_risk_state | healthy, slipping, at_risk |
| risk_pattern | Same as above, except some at_risk accounts are `silent`: they go quiet instead of opening more tickets |
| deterioration_start | Date the account started declining (blank for healthy) |
| churned / churn_date | Whether and when the account left before the snapshot; churned accounts have no tickets after that date |

## What was planted

After `deterioration_start`, the effects ramp up over about 90 days:

| Pattern | Share | Ticket volume | Resolution time | Satisfaction | Repeat contacts | Stuck tickets | Churn by snapshot |
|---|---|---|---|---|---|---|---|
| healthy | ~70% | baseline | baseline | ~4 | low | rare | ~4% |
| slipping | ~17% | ~1.5× | slower | ~3.3 | higher | more | ~15% |
| at_risk | ~9% | ~2× | much slower | ~2.8 | much higher | many | ~55% |
| silent | ~4% | ~0.5× | slower | ~2.5 | low | many | ~70% |

Deliberate noise, so the score can't be perfect:
- Every new account has an onboarding burst in its first 60 days. This looks like a volume spike but isn't a risk.
- About 15% of healthy accounts have a one-off 3-week incident spike.
- All signals are random draws. A naive volume + satisfaction score separates healthy from non-healthy accounts with an AUC around 0.8, not 1.0.
- Silent accounts will be missed by volume-based signals. Reporting that honestly is part of the exercise.

Out of the box, `seed 42` gives 278 healthy, 69 slipping, 37 at_risk and 16 silent accounts, with 52 churned.
