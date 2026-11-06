"""
Synthetic account + support-ticket generator for the customer health score
(Workstream 4 of the Support Operations Analytics project).

Scenario: a vendor of cloud-based cardiac imaging analysis software sells to
hospitals, imaging centers and cardiology practices. Each account has a HIDDEN
risk state that shapes its ticket history. The health score never sees the
hidden labels; they are written to a separate truth file and used only to
evaluate the score afterwards.

Planted patterns (what a good score should be able to pick up):
  healthy   - steady ticket volume, normal resolution times, CSAT ~4
  slipping  - after a deterioration date: more tickets, slower resolution,
              lower CSAT, more repeat contacts, moderate churn risk
  at_risk   - same direction, stronger; high churn risk
  at_risk/silent - a subset of at-risk accounts that go QUIET instead of loud
              (fewer tickets, poor CSAT when they do respond). Volume-based
              signals will tend to miss these; that's deliberate and realistic.
Noise on purpose:
  - every new account has an onboarding burst in its first ~60 days
  - some healthy accounts get a one-off incident spike
  - all signals are noisy; nothing separates the groups perfectly

Usage:
  python generate_health_data.py                # writes ./data and ./truth
  python generate_health_data.py --seed 7 --accounts 500 --out ./somewhere
"""
import argparse
import os

import numpy as np
import pandas as pd

START = pd.Timestamp("2025-07-01")
SNAPSHOT = pd.Timestamp("2026-10-31 23:59:59")   # "today" for the dataset

SEGMENTS = {  # segment: (share, seat range, annual contract value per seat)
    "Hospital system":     (0.30, (40, 250), 1800),
    "Community hospital":  (0.25, (15, 60), 1600),
    "Imaging center":      (0.25, (5, 30), 1500),
    "Cardiology practice": (0.20, (3, 15), 1400),
}
REGIONS = ["West", "Mountain", "Midwest", "Northeast", "Southeast", "Southwest"]
TIERS = ["Standard", "Professional", "Enterprise"]

CATEGORIES = {  # category: (base weight, example subjects)
    "Login & access":           (0.16, ["Locked out after password reset", "SSO login failing for radiology staff", "New user cannot access worklist"]),
    "Image upload & transfer":  (0.17, ["CT series stuck in upload queue", "DICOM transfer failing from scanner", "Upload very slow since yesterday"]),
    "Analysis report delay":    (0.13, ["Report not returned within expected time", "Analysis pending for over 24 hours", "Need status on urgent case"]),
    "Report content question":  (0.10, ["Question about values in analysis report", "Report shows unexpected result", "Clarify measurement in report"]),
    "EHR/PACS integration":     (0.11, ["Results not appearing in EHR", "PACS integration error after upgrade", "HL7 messages rejected"]),
    "Billing & invoicing":      (0.10, ["Invoice does not match contract", "Question about per-case charges", "Need updated W-9 / billing contact"]),
    "Training request":         (0.12, ["Training for new technologists", "Refresher session for ordering physicians", "Onboarding new site staff"]),
    "Feature request":          (0.06, ["Request: export report to PDF", "Request: bulk case status view", "Request: additional user roles"]),
    "Account & contract":       (0.05, ["Add a new site to the contract", "Change primary admin contact", "Question about renewal terms"]),
}
# categories that get heavier when an account is deteriorating
PAIN_CATEGORIES = ["Image upload & transfer", "Analysis report delay", "EHR/PACS integration", "Billing & invoicing"]

PRIORITIES = ["Low", "Medium", "High", "Critical"]
FIRST_RESPONSE_MEDIAN_H = {"Low": 10, "Medium": 5, "High": 1.5, "Critical": 0.4}
RESOLUTION_MEDIAN_H = {"Low": 70, "Medium": 36, "High": 16, "Critical": 6}
CHANNELS = ["Email", "Phone", "Portal", "Chat"]

STATE_PARAMS = {
    #            volume mult, resolution mult, CSAT shift, repeat prob, high-priority shift, churn prob,
    #            stall prob (ticket gets stuck: resolution time x8-25)
    "healthy":  dict(vol=1.0, res=1.0, csat=0.0,  repeat=0.07, hipri=0.00, churn=0.04, stall=0.015),
    "slipping": dict(vol=1.6, res=1.35, csat=-0.6, repeat=0.18, hipri=0.08, churn=0.25, stall=0.05),
    "at_risk":  dict(vol=2.4, res=1.8, csat=-1.3, repeat=0.32, hipri=0.15, churn=0.60, stall=0.09),
    "silent":   dict(vol=0.35, res=1.4, csat=-1.7, repeat=0.10, hipri=0.05, churn=0.65, stall=0.12),
}

NAME_A = ["Mercy", "St. Luke's", "Valley", "Riverside", "Summit", "Bayview", "Cedar", "Pinecrest", "Lakeshore",
          "Northgate", "Harbor", "Sierra", "Oakwood", "Granite", "Redwood", "Prairie", "Coastal", "Hillcrest",
          "Meadowbrook", "Fairview", "Westbrook", "Clearwater", "Highland", "Silver Lake", "Canyon", "Brookside"]
NAME_B = {"Hospital system": ["Health System", "Health Network", "Medical Group"],
          "Community hospital": ["Community Hospital", "Regional Medical Center", "Memorial Hospital"],
          "Imaging center": ["Imaging", "Diagnostic Imaging", "Radiology Partners"],
          "Cardiology practice": ["Heart & Vascular", "Cardiology Associates", "Heart Clinic"]}


def make_accounts(rng, n):
    segs = list(SEGMENTS)
    seg = rng.choice(segs, size=n, p=[SEGMENTS[s][0] for s in segs])
    rows, used = [], set()
    for i in range(n):
        s = seg[i]
        lo, hi = SEGMENTS[s][1]
        seats = int(rng.integers(lo, hi + 1))
        while True:
            name = f"{rng.choice(NAME_A)} {rng.choice(NAME_B[s])}"
            if name not in used:
                break
            name = f"{name} {rng.choice(REGIONS)}"
            if name not in used:
                break
        used.add(name)
        # ~70% were customers before the window starts; the rest onboard during it
        if rng.random() < 0.7:
            contract_start = START - pd.Timedelta(days=int(rng.integers(60, 1100)))
        else:
            contract_start = START + pd.Timedelta(days=int(rng.integers(0, 330)))
        tier = rng.choice(TIERS, p=[0.35, 0.45, 0.20] if s in ("Hospital system", "Community hospital") else [0.6, 0.35, 0.05])
        rows.append(dict(
            account_id=f"ACC-{1001 + i}",
            account_name=name,
            segment=s,
            region=rng.choice(REGIONS),
            product_tier=tier,
            seats=seats,
            contract_start_date=contract_start.date(),
            annual_contract_value=int(round(seats * SEGMENTS[s][2] * rng.uniform(0.85, 1.15), -2)),
        ))
    return pd.DataFrame(rows)


def assign_truth(rng, accounts):
    rows = []
    for a in accounts.itertuples():
        state = rng.choice(["healthy", "slipping", "at_risk"], p=[0.68, 0.19, 0.13])
        pattern = state
        if state == "at_risk" and rng.random() < 0.25:
            pattern = "silent"
        obs_start = max(START, pd.Timestamp(a.contract_start_date))
        deterioration = pd.NaT
        if state != "healthy":
            # starts somewhere between month 4 and month 12 of the window, after onboarding
            earliest = max(obs_start + pd.Timedelta(days=75), START + pd.Timedelta(days=120))
            latest = START + pd.Timedelta(days=370)
            if earliest >= latest:
                earliest = latest - pd.Timedelta(days=30)
            deterioration = earliest + pd.Timedelta(days=int(rng.integers(0, (latest - earliest).days + 1)))
        churned, churn_date = False, pd.NaT
        if rng.random() < STATE_PARAMS[pattern]["churn"]:
            base = deterioration if state != "healthy" else obs_start + pd.Timedelta(days=int(rng.integers(120, 480)))
            cd = base + pd.Timedelta(days=int(rng.integers(45, 160)))
            if cd <= SNAPSHOT:
                churned, churn_date = True, cd.normalize()
        rows.append(dict(account_id=a.account_id, true_risk_state=state, risk_pattern=pattern,
                         deterioration_start=deterioration.date() if pd.notna(deterioration) else None,
                         churned=churned, churn_date=churn_date.date() if pd.notna(churn_date) else None))
    return pd.DataFrame(rows)


def lognormal(rng, median, sigma):
    return float(np.exp(np.log(median) + sigma * rng.standard_normal()))


def make_tickets(rng, accounts, truth):
    cats = list(CATEGORIES)
    base_w = np.array([CATEGORIES[c][0] for c in cats])
    t = truth.set_index("account_id")
    rows = []
    days = pd.date_range(START, SNAPSHOT.normalize(), freq="D")
    for a in accounts.itertuples():
        tr = t.loc[a.account_id]
        p = STATE_PARAMS[tr.risk_pattern]
        obs_start = max(START, pd.Timestamp(a.contract_start_date))
        end = pd.Timestamp(tr.churn_date) if tr.churned else SNAPSHOT.normalize()
        det = pd.Timestamp(tr.deterioration_start) if tr.deterioration_start else None
        weekly = 0.12 + 0.045 * np.sqrt(a.seats) * 6 * rng.uniform(0.7, 1.3)   # base tickets/week, scales with size
        weekly = weekly / 7 * 0.55
        # optional one-off incident spike for some healthy accounts (false-positive bait)
        spike_start = None
        if tr.risk_pattern == "healthy" and rng.random() < 0.15:
            spike_start = START + pd.Timedelta(days=int(rng.integers(30, 470)))
        recent = []  # (created, category) for planting repeat contacts
        for d in days:
            if d < obs_start or d > end:
                continue
            rate = weekly
            if (d - pd.Timestamp(a.contract_start_date)).days < 60:
                rate *= 2.5                                             # onboarding burst
            ramp = 0.0
            if det is not None and d >= det:
                ramp = min(1.0, (d - det).days / 90)                    # deteriorates over ~3 months
                rate *= 1 + (p["vol"] - 1) * ramp
            if spike_start is not None and 0 <= (d - spike_start).days < 21:
                rate *= 3.0
            if d.dayofweek >= 5:
                rate *= 0.3
            for _ in range(rng.poisson(rate)):
                created = d + pd.Timedelta(minutes=int(rng.normal(13 * 60, 150)) % (24 * 60))
                # repeat contact on a recent issue?
                recent = [(c, k) for c, k in recent if (created - c).days <= 30]
                repeat_p = p["repeat"] * ramp + STATE_PARAMS["healthy"]["repeat"] * (1 - ramp)
                if recent and rng.random() < repeat_p:
                    cat = recent[int(rng.integers(len(recent)))][1]
                    is_follow_up = True
                else:
                    w = base_w.copy()
                    if ramp > 0:
                        for c in PAIN_CATEGORIES:
                            w[cats.index(c)] *= 1 + 1.2 * ramp
                    if (d - pd.Timestamp(a.contract_start_date)).days < 60:
                        w[cats.index("Training request")] *= 3
                    cat = rng.choice(cats, p=w / w.sum())
                    is_follow_up = False
                recent.append((created, cat))
                hip = p["hipri"] * ramp
                pri = rng.choice(PRIORITIES, p=[0.30 - hip / 2, 0.42 - hip / 2, 0.20 + hip * 0.6, 0.08 + hip * 0.4])
                frt_h = lognormal(rng, FIRST_RESPONSE_MEDIAN_H[pri] * (1 + (p["res"] - 1) * ramp * 0.5), 0.8)
                res_h = lognormal(rng, RESOLUTION_MEDIAN_H[pri] * (1 + (p["res"] - 1) * ramp), 1.0)
                stall_p = STATE_PARAMS["healthy"]["stall"] * (1 - ramp) + p["stall"] * ramp
                if rng.random() < stall_p:
                    res_h *= rng.uniform(8, 25)                          # stuck ticket
                res_h = max(res_h, frt_h + 0.25)
                first_resp = created + pd.Timedelta(hours=frt_h)
                resolved = created + pd.Timedelta(hours=res_h)
                if resolved <= SNAPSHOT:
                    status = "Closed"
                else:
                    resolved = pd.NaT
                    status = rng.choice(["Open", "Pending customer"], p=[0.7, 0.3])
                if first_resp > SNAPSHOT:
                    first_resp = pd.NaT
                csat = np.nan
                if status == "Closed" and rng.random() < 0.42:             # survey response rate
                    mu = 4.2 + p["csat"] * ramp - 0.35 * np.log(res_h / RESOLUTION_MEDIAN_H[pri]) - (0.3 if is_follow_up else 0)
                    csat = float(np.clip(round(rng.normal(mu, 0.8)), 1, 5))
                rows.append(dict(
                    account_id=a.account_id,
                    created_at=created.floor("min"),
                    first_response_at=first_resp.floor("min") if pd.notna(first_resp) else pd.NaT,
                    resolved_at=resolved.floor("min") if pd.notna(resolved) else pd.NaT,
                    status=status,
                    priority=pri,
                    channel=rng.choice(CHANNELS, p=[0.38, 0.24, 0.28, 0.10]),
                    category=cat,
                    subject=rng.choice(CATEGORIES[cat][1]),
                    satisfaction_rating=csat,
                ))
    tickets = pd.DataFrame(rows).sort_values("created_at").reset_index(drop=True)
    tickets.insert(0, "ticket_id", [f"TCK-{100001 + i}" for i in range(len(tickets))])
    return tickets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--accounts", type=int, default=400)
    ap.add_argument("--out", default=".")
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)

    accounts = make_accounts(rng, args.accounts)
    truth = assign_truth(rng, accounts)
    tickets = make_tickets(rng, accounts, truth)

    data_dir, truth_dir = os.path.join(args.out, "data"), os.path.join(args.out, "truth")
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(truth_dir, exist_ok=True)
    accounts.to_csv(os.path.join(data_dir, "accounts.csv"), index=False)
    tickets.to_csv(os.path.join(data_dir, "tickets.csv"), index=False)
    truth.to_csv(os.path.join(truth_dir, "account_truth.csv"), index=False)
    print(f"accounts: {len(accounts)}  tickets: {len(tickets)}  churned: {truth.churned.sum()}")
    print(truth.risk_pattern.value_counts().to_string())


if __name__ == "__main__":
    main()
