import csv
def load(p):
    out = {}
    with open(p, newline="", encoding="utf-8") as f:
        rdr = csv.reader(f)
        hdr = next(rdr)
        for row in rdr:
            out[row[0]] = row[1:]
    return hdr, out

h14, d14 = load(r"c:\All_repos\openstudio-ee-gem\lib\parametric_run\simulations\run_test_014_custom_rsmeans\parametric_results.csv")
h15, d15 = load(r"c:\All_repos\openstudio-ee-gem\lib\parametric_run\simulations\run_test_015_custom_rsmeans\parametric_results.csv")

print(f"014 rows: {len(d14)}  015 rows: {len(d15)}")
only14 = sorted(set(d14) - set(d15))
only15 = sorted(set(d15) - set(d14))
print(f"Keys only in 014 ({len(only14)}):"); [print(" ", k) for k in only14]
print(f"Keys only in 015 ({len(only15)}):"); [print(" ", k) for k in only15]

# Focus on cost / source columns.
cols = h15[1:]  # baseline + 3 scenarios
print()
print("=" * 100)
print(f"{'METRIC':70s} | {'baseline':>14s} | {'sc1':>14s} | {'sc2':>14s} | {'sc3':>14s}")
print("=" * 100)
cost_keys = sorted([k for k in d14 if k in d15 and (
    "cost" in k.lower()
    or "source" in k.lower()
    or "basis" in k.lower()
    or k in ("scenario","total_construction_cost_usd","total_additional_construction_cost_usd")
)])
for k in cost_keys:
    a = d14[k]; b = d15[k]
    # only print rows that differ in any column
    if a == b: continue
    def fmt(x):
        try:
            return f"{float(x):>14.2f}"
        except Exception:
            return f"{(str(x) or '-')[:14]:>14s}"
    print(f"{k[:70]:70s} | 14: {fmt(a[0])} {fmt(a[1])} {fmt(a[2])} {fmt(a[3])}")
    print(f"{'':70s} | 15: {fmt(b[0])} {fmt(b[1])} {fmt(b[2])} {fmt(b[3])}")
