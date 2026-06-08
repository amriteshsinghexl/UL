"""
AST-based formula extractor for ULP model output variables.

Walks the model source files with Python's ast module to pull out the actual
Python source snippet for each output variable assignment, then pairs that
snippet with a hand-crafted human-readable formula and dependency list.

Usage
-----
    from app.formula_extractor import get_formula_registry

    registry = get_formula_registry()   # list[FormulaEntry]
    for entry in registry:
        print(entry["name"], "→", entry["formula"])
"""
from __future__ import annotations

import ast
import textwrap
from pathlib import Path
from typing import Any

_MODEL_DIR = Path(__file__).parent.parent / "ulp_model"

# ---------------------------------------------------------------------------
# Static formula registry
# Each entry is the ground-truth formula metadata for one CSV output column.
# python_source is filled in at runtime by _enrich_with_ast().
# ---------------------------------------------------------------------------

_REGISTRY: list[dict[str, Any]] = [
    # ------------------------------------------------------------------
    # Part 2 — Decrements
    # ------------------------------------------------------------------
    {
        "name": "no_pols_ifsm",
        "display_name": "Policies IF (Start of Month)",
        "formula": "max(no_pols_if[t-1] − no_mats[t-1], 0)",
        "depends_on": ["no_pols_if", "no_mats"],
        "part": "Part 2 — Decrements",
        "description": (
            "Policies in force at start of month t, after removing last period's maturities."
        ),
        "python_source": None,
    },
    {
        "name": "no_deaths",
        "display_name": "Number of Deaths",
        "formula": "no_pols_ifsm[t] × m_death_rate[t]",
        "depends_on": ["no_pols_ifsm"],
        "part": "Part 2 — Decrements",
        "description": (
            "Deaths = start-of-month policies × monthly death rate derived from "
            "select/ultimate mortality tables (per mille ÷ 1000), converted to monthly: "
            "m_death_rate = 1 − (1 − ann_death_rate)^(1/12)."
        ),
        "python_source": None,
    },
    {
        "name": "no_surrs",
        "display_name": "Number of Surrenders",
        "formula": "(no_pols_ifsm[t] − no_deaths[t]) × m_lapse_rate[t]",
        "depends_on": ["no_pols_ifsm", "no_deaths"],
        "part": "Part 2 — Decrements",
        "description": (
            "Surrenders = surviving policies (after deaths) × monthly lapse rate. "
            "Lapse rate varies by policy year and premium payment frequency."
        ),
        "python_source": None,
    },
    {
        "name": "no_mats",
        "display_name": "Number of Maturities",
        "formula": "(no_pols_ifsm[t] − no_deaths[t] − no_surrs[t]) × 𝟙[t = pol_term × 12]",
        "depends_on": ["no_pols_ifsm", "no_deaths", "no_surrs"],
        "part": "Part 2 — Decrements",
        "description": (
            "Maturities occur only at the final month of the policy term. "
            "All net survivors at that month are recorded as maturities."
        ),
        "python_source": None,
    },
    {
        "name": "no_pols_if",
        "display_name": "Policies In Force (End of Month)",
        "formula": "no_pols_ifsm[t] − no_deaths[t] − no_surrs[t] − no_mats[t]",
        "depends_on": ["no_pols_ifsm", "no_deaths", "no_surrs", "no_mats"],
        "part": "Part 2 — Decrements",
        "description": "Policies in force at end of month after all decrements.",
        "python_source": None,
    },
    # ------------------------------------------------------------------
    # Part 3 Pass 1 — Cashflow components
    # ------------------------------------------------------------------
    {
        "name": "basic_prem_if",
        "display_name": "Basic Premium Income",
        "formula": "basic_prem_pp[t] × no_pols_ifsm[t]",
        "depends_on": ["no_pols_ifsm"],
        "part": "Part 3 Pass 1 — Cashflows",
        "description": (
            "Total basic premium income. basic_prem_pp is the per-policy annualized "
            "committed premium (ACP × freq_months / 12), applied only on premium due dates "
            "within the premium payment term."
        ),
        "python_source": None,
    },
    {
        "name": "topup_prem_if",
        "display_name": "Top-Up Premium Income",
        "formula": "topup_prem_pp[t] × no_pols_ifsm[t]",
        "depends_on": ["no_pols_ifsm"],
        "part": "Part 3 Pass 1 — Cashflows",
        "description": (
            "Total top-up premium income. topup_prem_pp is the per-policy annualized "
            "top-up premium (ATP × topup_freq_months / 12)."
        ),
        "python_source": None,
    },
    {
        "name": "prem_inc_if",
        "display_name": "Total Premium Income",
        "formula": "basic_prem_if[t] + topup_prem_if[t]",
        "depends_on": ["basic_prem_if", "topup_prem_if"],
        "part": "Part 3 Pass 1 — Cashflows",
        "description": "Total premium income = basic premium + top-up premium.",
        "python_source": None,
    },
    {
        "name": "op_init_exp_if",
        "display_name": "Initial Operating Expenses",
        "formula": (
            "(op_exp_per_pol[0] / 12) × no_pols_ifsm[t] + (op_exp_per_prem[0] / 100) × basic_prem_if[t]"
            "  [Year 1 only; zero thereafter]"
        ),
        "depends_on": ["no_pols_ifsm", "basic_prem_if"],
        "part": "Part 3 Pass 1 — Cashflows",
        "description": (
            "Year-1 expenses: fixed monthly per-policy cost + percentage of basic premium. "
            "Zero in all subsequent policy years."
        ),
        "python_source": None,
    },
    {
        "name": "op_ren_exp_if",
        "display_name": "Renewal Operating Expenses",
        "formula": (
            "((op_exp_per_pol[1] / 12) × (1 + inf_pc/100)^((t−1)/12) × no_pols_ifsm[t]"
            " + (op_exp_per_prem[1] / 100) × basic_prem_if[t])  [Years 2+; zero in Year 1]"
        ),
        "depends_on": ["no_pols_ifsm", "basic_prem_if"],
        "part": "Part 3 Pass 1 — Cashflows",
        "description": (
            "Renewal expenses with expense inflation. Fixed component is indexed by "
            "(1 + inf_pc/100)^((t−1)/12) from policy inception."
        ),
        "python_source": None,
    },
    {
        "name": "invt_exp_if",
        "display_name": "Investment Expenses",
        "formula": "av_ad[t] × (ann_fme_pc / 12 / 100) × no_pols_ifsm[t]",
        "depends_on": ["no_pols_ifsm"],
        "part": "Part 3 Pass 1 — Cashflows",
        "description": (
            "Fund management expenses = AV after deductions × monthly FME rate × policies. "
            "ann_fme_pc is the annual fund management expense as a percentage."
        ),
        "python_source": None,
    },
    {
        "name": "comm_if",
        "display_name": "Commission",
        "formula": "comm_basic_pc[py] × basic_prem_if[t] + comm_topup_pc[py] × topup_prem_if[t]",
        "depends_on": ["basic_prem_if", "topup_prem_if"],
        "part": "Part 3 Pass 1 — Cashflows",
        "description": (
            "Commission = basic commission rate × basic premium + top-up rate × top-up premium. "
            "Rates are policy-year-indexed from the commission table."
        ),
        "python_source": None,
    },
    {
        "name": "ovrd_if",
        "display_name": "Override Commission",
        "formula": "ovrd_pc[py] × basic_prem_if[t]",
        "depends_on": ["basic_prem_if"],
        "part": "Part 3 Pass 1 — Cashflows",
        "description": (
            "Override commission paid to sales management = override rate (policy-year "
            "dependent) × basic premium income."
        ),
        "python_source": None,
    },
    {
        "name": "death_outgo",
        "display_name": "Death Benefit Outgo",
        "formula": "death_ben_pp[t] × no_deaths[t]",
        "depends_on": ["no_deaths"],
        "part": "Part 3 Pass 1 — Cashflows",
        "description": (
            "Total death claim payments. Per-policy death benefit:\n"
            "  Option 1 (db_opt=1): max(sum_assured × lien_pc, bav_bval_bb) + tuav_bval_bb\n"
            "  Option 2 (db_opt=2): sum_assured × lien_pc + bav_bval_bb + tuav_bval_bb"
        ),
        "python_source": None,
    },
    {
        "name": "surr_outgo",
        "display_name": "Surrender Benefit Outgo",
        "formula": "surr_ben_pp[t] × no_surrs[t]",
        "depends_on": ["no_surrs"],
        "part": "Part 3 Pass 1 — Cashflows",
        "description": (
            "Total surrender payments. surr_ben_pp = bav_bval_bb + tuav_bval_bb − surr_chg_pp, "
            "where surr_chg_pp = min(surr_chg[py]/100 × ACP, bav_bval_bb)."
        ),
        "python_source": None,
    },
    {
        "name": "mat_outgo",
        "display_name": "Maturity Benefit Outgo",
        "formula": "av_ab[t] × no_mats[t]",
        "depends_on": ["no_mats"],
        "part": "Part 3 Pass 1 — Cashflows",
        "description": "Total maturity payments = end-of-month account value × number of maturities.",
        "python_source": None,
    },
    {
        "name": "cog_term_adj",
        "display_name": "Cost-of-Guarantee on Terminations",
        "formula": "cog_death[t] + cog_surr[t] + cog_mat[t]",
        "depends_on": ["no_deaths", "no_surrs", "no_mats"],
        "part": "Part 3 Pass 1 — Cashflows",
        "description": (
            "Additional cost when guaranteed AV (tracked at hard guarantee rate) exceeds "
            "actual AV on death/surrender/maturity events:\n"
            "  cog_death = max(g_death_ben − death_ben, 0) × no_deaths\n"
            "  cog_surr  = max(g_surr_ben − surr_ben, 0) × no_surrs\n"
            "  cog_mat   = max(g_bav_ab + g_tuav_ab − av_ab, 0) × no_mats"
        ),
        "python_source": None,
    },
    {
        "name": "unit_res_bgn",
        "display_name": "Unit Reserve (Start of Month)",
        "formula": "av_ab[t−1] × no_pols_ifsm[t]",
        "depends_on": ["no_pols_ifsm"],
        "part": "Part 3 Pass 1 — Cashflows",
        "description": "Unit reserve at start of month = prior end-of-month AV × policies at start of month.",
        "python_source": None,
    },
    {
        "name": "unit_res_end",
        "display_name": "Unit Reserve (End of Month)",
        "formula": "av_ab[t] × no_pols_if[t] × (1 − 𝟙[t = pol_term × 12])",
        "depends_on": ["no_pols_if"],
        "part": "Part 3 Pass 1 — Cashflows",
        "description": (
            "Unit reserve at end of month = end AV × surviving policies. "
            "Set to zero at the maturity month."
        ),
        "python_source": None,
    },
    {
        "name": "unit_inc",
        "display_name": "Unit Fund Income",
        "formula": "av_ad[t] × m_ulp_fer[t] × no_pols_ifsm[t]",
        "depends_on": ["no_pols_ifsm"],
        "part": "Part 3 Pass 1 — Cashflows",
        "description": (
            "Investment return on the unit fund. m_ulp_fer = (1 + ann_ulp_fer/100)^(1/12) − 1 "
            "is the monthly fund return after allowing for fund charges (ann_fmc_pc)."
        ),
        "python_source": None,
    },
    {
        "name": "non_unit_inc",
        "display_name": "Non-Unit Income",
        "formula": (
            "(alloc_chg_basic + alloc_chg_topup + tot_dedn_act) × no_pols_ifsm[t]"
            " − op_init_exp_if[t] − op_ren_exp_if[t] − invt_exp_if[t]"
            " − comm_if[t] − ovrd_if[t]) × m_sh_fer × is_inforce_bgn[t]"
        ),
        "depends_on": ["no_pols_ifsm", "op_init_exp_if", "op_ren_exp_if", "invt_exp_if", "comm_if", "ovrd_if"],
        "part": "Part 3 Pass 1 — Cashflows",
        "description": (
            "Investment return on shareholder (non-unit) funds. "
            "m_sh_fer = (1 + ann_sh_fer/100)^(1/12) − 1."
        ),
        "python_source": None,
    },
    {
        "name": "cf_before_zv",
        "display_name": "Cashflow Before Zeroising",
        "formula": (
            "unit_res_bgn[t] + prem_inc_if[t] + unit_inc[t] + non_unit_inc[t]"
            " − op_init_exp_if[t] − op_ren_exp_if[t] − invt_exp_if[t]"
            " − comm_if[t] − ovrd_if[t] − death_outgo[t] − surr_outgo[t]"
            " − mat_outgo[t] − cog_term_adj[t] − unit_res_end[t]"
        ),
        "depends_on": [
            "unit_res_bgn", "prem_inc_if", "unit_inc", "non_unit_inc",
            "op_init_exp_if", "op_ren_exp_if", "invt_exp_if",
            "comm_if", "ovrd_if", "death_outgo", "surr_outgo",
            "mat_outgo", "cog_term_adj", "unit_res_end",
        ],
        "part": "Part 3 Pass 1 — Cashflows",
        "description": "Net shareholder cashflow before zeroising reserve adjustment (S3.49).",
        "python_source": None,
    },
    # ------------------------------------------------------------------
    # Pass 2 — Backward: Zeroising Reserve
    # ------------------------------------------------------------------
    {
        "name": "zeroising_res_if",
        "display_name": "Zeroising Reserve",
        "formula": "max((zeroising_res_if[t+1] − cf_before_zv[t+1]) / (1 + m_vir), 0)   [backward]",
        "depends_on": ["cf_before_zv"],
        "part": "Pass 2 — Backward (Zeroising)",
        "description": (
            "Backward-pass reserve ensuring future cashflows are non-negative. "
            "m_vir = (1 + ann_vir/100)^(1/12) − 1 is the monthly valuation interest rate. "
            "Zero at t=0 and at/after maturity."
        ),
        "python_source": None,
    },
    # ------------------------------------------------------------------
    # Pass 3 — Forward: Tax & SCR
    # ------------------------------------------------------------------
    {
        "name": "cf_after_zv",
        "display_name": "Cashflow After Zeroising",
        "formula": "cf_before_zv[t] − zeroising_res_if[t] + zeroising_res_if[t−1] × (1 + m_vir)",
        "depends_on": ["cf_before_zv", "zeroising_res_if"],
        "part": "Pass 3 — Forward (Tax & SCR)",
        "description": "Cashflow after releasing/building the zeroising reserve (S3.54).",
        "python_source": None,
    },
    {
        "name": "op_tax",
        "display_name": "Operating Tax",
        "formula": "(tax_pc / 100) × cf_after_zv[t]",
        "depends_on": ["cf_after_zv"],
        "part": "Pass 3 — Forward (Tax & SCR)",
        "description": "Tax on shareholder cashflow at the statutory corporate tax rate (tax_pc %).",
        "python_source": None,
    },
    {
        "name": "cf_after_tax",
        "display_name": "Cashflow After Tax",
        "formula": "cf_after_zv[t] − op_tax[t]",
        "depends_on": ["cf_after_zv", "op_tax"],
        "part": "Pass 3 — Forward (Tax & SCR)",
        "description": "Post-tax shareholder cashflow.",
        "python_source": None,
    },
    {
        "name": "tot_res_if",
        "display_name": "Total Reserve",
        "formula": "unit_res_end[t] + zeroising_res_if[t]",
        "depends_on": ["unit_res_end", "zeroising_res_if"],
        "part": "Pass 3 — Forward (Tax & SCR)",
        "description": "Total policy reserve = unit reserve + zeroising (non-unit) reserve.",
        "python_source": None,
    },
    {
        "name": "solv_cap_req",
        "display_name": "Solvency Capital Requirement (SCR)",
        "formula": (
            "(solv_marg_res/100) × tot_res_if[t]"
            " + (solv_marg_sar/100) × max(death_ben × no_pols_if[t] − tot_res_if[t], 0)"
        ),
        "depends_on": ["tot_res_if", "no_pols_if"],
        "part": "Pass 3 — Forward (Tax & SCR)",
        "description": (
            "Required solvency capital = % of reserve margin + % of net sum-at-risk. "
            "Zero at t=0 and at/after maturity."
        ),
        "python_source": None,
    },
    {
        "name": "scr_inv_inc",
        "display_name": "SCR Investment Income",
        "formula": "solv_cap_req[t−1] × m_sh_fer",
        "depends_on": ["solv_cap_req"],
        "part": "Pass 3 — Forward (Tax & SCR)",
        "description": (
            "Investment return earned on the prior-period solvency capital. "
            "m_sh_fer = (1 + ann_sh_fer/100)^(1/12) − 1."
        ),
        "python_source": None,
    },
    {
        "name": "scr_inc_tax",
        "display_name": "SCR Income Tax",
        "formula": "(tax_pc / 100) × scr_inv_inc[t]",
        "depends_on": ["scr_inv_inc"],
        "part": "Pass 3 — Forward (Tax & SCR)",
        "description": "Tax on investment income earned on SCR capital.",
        "python_source": None,
    },
    {
        "name": "cf_after_scr",
        "display_name": "Cashflow After SCR",
        "formula": (
            "cf_after_tax[t] + solv_cap_req[t−1] − solv_cap_req[t]"
            " + scr_inv_inc[t] − scr_inc_tax[t]"
        ),
        "depends_on": ["cf_after_tax", "solv_cap_req", "scr_inv_inc", "scr_inc_tax"],
        "part": "Pass 3 — Forward (Tax & SCR)",
        "description": "Shareholder cashflow after all solvency capital movements (S3.64).",
        "python_source": None,
    },
    # ------------------------------------------------------------------
    # Pass 4 — Backward: Present Values
    # ------------------------------------------------------------------
    {
        "name": "pv_cf_after_scr",
        "display_name": "PV of Cashflow After SCR",
        "formula": "(pv_cf_after_scr[t+1] + cf_after_scr[t+1]) / (1 + m_rdr)   [backward]",
        "depends_on": ["cf_after_scr"],
        "part": "Pass 4 — Backward (Present Values)",
        "description": (
            "Present value at t of all future shareholder cashflows, "
            "discounted at the monthly risk discount rate m_rdr = (1 + ann_rdr/100)^(1/12) − 1."
        ),
        "python_source": None,
    },
    {
        "name": "pv_prem_inc",
        "display_name": "PV of Premium Income",
        "formula": "(pv_prem_inc[t+1] + prem_inc_if[t+1]) / (1 + m_rdr)   [backward]",
        "depends_on": ["prem_inc_if"],
        "part": "Pass 4 — Backward (Present Values)",
        "description": (
            "Present value at t of all future premium income, "
            "discounted at the same risk discount rate as pv_cf_after_scr."
        ),
        "python_source": None,
    },
]


# ---------------------------------------------------------------------------
# AST helpers — extract Python source for each output variable
# ---------------------------------------------------------------------------

def _extract_assignments(source: str, targets: set[str]) -> dict[str, str]:
    """
    Parse *source* with ast and return a dict mapping each name in *targets*
    to the dedented source snippet of its most-recent assignment RHS.

    Handles:
      self.<name>[:, t] = <expr>   (tensor slice assign)
      self.<name> = <expr>
      <name> = <expr>              (local variable)
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}

    lines = source.splitlines()
    found: dict[str, str] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue

        for tgt in node.targets:
            name = _resolve_target_name(tgt)
            if name not in targets:
                continue

            start = node.lineno - 1
            end = node.end_lineno if hasattr(node, "end_lineno") else start
            snippet = "\n".join(lines[start:end])
            found[name] = textwrap.dedent(snippet).strip()

    return found


def _resolve_target_name(node: ast.expr) -> str:
    """Return the bare variable name for simple assignment targets."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    # self.x[:, t] = ...  → Subscript whose value is Attribute
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
        return node.value.attr
    return ""


def _enrich_with_ast(registry: list[dict[str, Any]]) -> None:
    """
    Walk the model source files with ast and fill in 'python_source' for each
    registry entry where a matching assignment can be found.
    """
    target_names = {e["name"] for e in registry}

    source_files = [
        _MODEL_DIR / "forward_projection.py",
        _MODEL_DIR / "part3_cashflows.py",
        _MODEL_DIR / "outputs.py",
    ]

    all_snippets: dict[str, str] = {}
    for path in source_files:
        if not path.exists():
            continue
        try:
            src = path.read_text(encoding="utf-8")
        except OSError:
            continue
        snippets = _extract_assignments(src, target_names)
        for name, snippet in snippets.items():
            if name not in all_snippets:
                all_snippets[name] = f"# {path.name}\n{snippet}"

    for entry in registry:
        entry["python_source"] = all_snippets.get(entry["name"])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_registry_cache: list[dict[str, Any]] | None = None


def get_formula_registry() -> list[dict[str, Any]]:
    """
    Return the enriched formula registry (cached after first call).

    Each entry is a dict with keys:
        name          : CSV column name
        display_name  : human-readable label
        formula       : mathematical formula string
        depends_on    : list[str] of other output column names
        part          : model stage (e.g. "Part 2 — Decrements")
        description   : longer explanation
        python_source : extracted Python code snippet (may be None)
    """
    global _registry_cache
    if _registry_cache is None:
        import copy
        registry = copy.deepcopy(_REGISTRY)
        _enrich_with_ast(registry)
        _registry_cache = registry
    return _registry_cache


def get_formula_by_name(name: str) -> dict[str, Any] | None:
    """Return the formula entry for a specific output variable name, or None."""
    return next((e for e in get_formula_registry() if e["name"] == name), None)


def get_formula_map() -> dict[str, dict[str, Any]]:
    """Return {name: entry} dict for quick lookup."""
    return {e["name"]: e for e in get_formula_registry()}
