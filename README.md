# Support Operations Analytics (Healthcare)

A portfolio project covering the core weekly work of a Customer Success or Support Operations analyst at a healthcare technology company:

- What are customers contacting support about, and is the AI classifying it correctly?
- Are we meeting response and resolution targets, and where is the backlog building?
- How many agents will we need next quarter if volume grows as forecast?
- Which customers show early warning signs of disengagement?

| Workstream | Focus | Data | Status |
|---|---|---|---|
| 1 | LLM ticket classification, validated against ground truth | Bitext customer support dataset | Planned |
| 2 | SLA, backlog and resolution KPIs in SQL (Snowflake + dbt) | NYC 311 service requests | Planned |
| 3 | Volume forecast (SARIMA) and staffing scenarios | NYC 311 service requests | Planned |
| 4 | Explainable customer health score | Simulated healthcare accounts | **Complete** |

Each workstream uses the dataset best suited to its question. The datasets describe different populations and are never joined.

**Workstream 4 headline:** 88% of red-flagged accounts were truly deteriorating (vs a 27% base rate), holding at 80% on an unseen test date. The score did not predict near-term churn, and the write-up below explains why.

---
## Workstream 4: Customer health score

**Question:** Which customer accounts show early warning signs of disengagement, and can a simple, explainable score find them?

**Notebook:** `04_customer_health_score.ipynb` · **Data:** `data/accounts.csv`, `data/tickets.csv` (generator: `generate_health_data.py`, seed 42)

> **Account and ticket data is simulated.** No public dataset combines account IDs, ticket history and customer outcomes, so the data was generated with planted risk patterns. That means the score can be validated against known outcomes. Hidden labels live in `truth/account_truth.csv` and are read only by the evaluation step.

### Scenario
There are 400 accounts (hospital systems, community hospitals, imaging centers and cardiology practices) of a cardiac-imaging software vendor, with about 22,500 support tickets from July 2025 to October 2026. Roughly 30% of accounts were secretly set to deteriorate partway through. Some got louder (more tickets, slower fixes, lower satisfaction), and a few went quiet instead. Deliberate noise makes a perfect score impossible: every new account has an onboarding ticket burst, some healthy accounts get one-off incident spikes, and survey responses are sparse.

### Method
Accounts are scored **as of a fixed date using only data visible on that date**. Tickets resolved later still count as open, and ratings submitted later are ignored. Each account starts at 100 and loses points on five signals. Each signal is scaled to a 0–1 penalty, and a signal with too little data costs nothing.

| Signal | Definition | Weight | Full penalty at |
|---|---|---|---|
| Low satisfaction | Mean CSAT, last 90 days (3+ ratings) | 30 | ≤ 2.0 of 5 |
| Ticket volume spike | Last 30 days vs the account's own 6-month baseline (onboarding excluded) | 20 | ≥ 2× baseline |
| Slow resolution | Median resolution time vs typical for the *same priority*, last 90 days | 20 | ≥ 2× typical |
| Repeat contacts | Share of last-30-day tickets in the same category as one within the prior 7 days | 15 | ≥ 50% |
| Stale high-priority ticket | Any High or Critical ticket open more than 7 days | 15 | any |

**Bands:** Green 80–100 · Yellow 60–79 · Red below 60. Every red account lists its **top contributing signal**, so a CSM can see why it's red.

Weights and thresholds are judgment calls, fixed before evaluation. They are starting points, not tuned values.

### Evaluation design
- **Design date: July 31, 2026.** The score was built and diagnosed here.
- **Test date: April 30, 2026.** It was scored once with no changes, as an out-of-sample check.
- Two questions were asked at each date: does the score rank *truly deteriorating* accounts as riskier (AUC), and does it predict *churn in the next 90 days*?

### Results

| | Design date (Jul 31) | Test date (Apr 30) |
|---|---|---|
| Accounts scored | 369 | 376 |
| Green / Yellow / Red | 277 / 75 / 17 | 312 / 59 / 5 |
| **Red accounts truly deteriorating** | **88%** (15 of 17), vs 27% of all accounts | **80%** (4 of 5), vs 29% of all accounts |
| AUC, deteriorating accounts | 0.72 | 0.59 |
| AUC, churn in next 90 days | 0.49 | 0.59 |
| 90-day churn rate, Green / Yellow / Red | 5.4% / 6.7% / 5.9% | 3.5% / 8.5% / 20.0% |

**What works:** the red list is precise. A CSM working it would rarely waste a call, and that held on the unseen date.

**What doesn't:** at the design date, the score did not predict 90-day churn (AUC 0.49), and 15 of the 21 accounts that churned were green. Diagnosis:
1. **No lead time.** Accounts that churned in August–October had been declining for a median of only 1.8 months on the as-of date, before their ticket signals were strong.
2. **The strongest decliners had already left.** 22 deteriorating accounts churned before July 31, so the red accounts that remained hadn't churned yet.
3. **Too little data scored as healthy.** Accounts with too few survey ratings got no satisfaction signal and defaulted toward green.

On the test date, churn rates did rise from Green to Yellow to Red. With only 5 red accounts that is encouraging, not conclusive.

### Tested and rejected: v2
A second version tried to fix the failures above: an **engagement-drop** signal for accounts going quiet, CSAT **shrinkage** toward the overall mean so accounts with 1–2 ratings still count, and an **"Insufficient data"** band in place of a default green.

| | v1 (Jul 31) | v2 (Jul 31) | v1 (Apr 30) | v2 (Apr 30) |
|---|---|---|---|---|
| AUC, deteriorating | **0.72** | 0.70 | **0.59** | 0.57 |
| Red accounts | 17 | 8 | 5 | 1 |
| Silent accounts caught | 3 of 9 | 3 of 9 | 1 of 14 | 0 of 14 |

v2 was worse on both dates, so **v1 is the final score.** Two lessons:
- **Ticket data can't reliably detect silence.** Most quiet-but-unhappy accounts are small practices that normally open 1–2 tickets a month. A drop to about 0.5 a month falls within normal random variation over 60 days. Detecting this needs **product usage data**, such as cases analyzed or logins per week, which production health scores combine with support data.
- **A second test date prevented a false win.** On July 31, the "Insufficient data" group looked predictive: 33% of it churned. On April 30 its churn rate was 6.7%, below Yellow's.

### Changes from the original plan
- **Repeat contacts:** the plan's "2+ contacts on the same issue in 30 days" marked 46% of all tickets as repeats, and mostly flagged large accounts for being large. It was changed to *same category within 7 days, as a share of recent tickets* (16% of tickets). Some size bias remains: 15% of hospital systems are flagged, vs 3% of cardiology practices.
- **Satisfaction:** the window is 90 days instead of 30, with a minimum of 3 ratings, because survey responses are too sparse for 30 days.
- **Resolution time:** priority-adjusted, so accounts that mostly log Low-priority tickets don't look slow by default.

### Limitations
- The data is synthetic: the patterns were planted by the same person who built the score. The results show that the *method* works on data with known structure, not how it would perform on any real customer base.
- Red groups are small (17 and 5 accounts), so the percentages carry wide uncertainty.
- Weights are expert judgment, not fitted. With real churn history, a logistic regression on the same signals would be the natural next step, keeping the signals explainable.

### Resume bullet
> Built an explainable customer health score (5 support signals, documented weights, top-reason per account) on 400 simulated healthcare accounts; 88% of red-flagged accounts were truly deteriorating vs a 27% base rate, holding at 80% on an unseen test date. Diagnosed why it missed near-term churn and tested a v2 that failed out of sample, so v1 was kept and the need for product-usage signals documented.
