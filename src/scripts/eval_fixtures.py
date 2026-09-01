"""
Hand-labeled eval cases for the real `farmacia_carmen_sanjuan` demo tenant
(the only tenant with a real product catalog — see data/clients/farmacia_carmen_sanjuan/products_catalog.csv).

Every `expected_products` entry is justified directly by that catalog's own
copy (see the comment on each case) rather than guessed — this is a small,
hand-verified test set, not a scraped or synthetic one.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvalCase:
    id: str
    query: str
    # Product names (as they appear in the CSV) that a correct answer should surface.
    expected_products: list[str] = field(default_factory=list)
    # True for queries about things the catalog genuinely does not sell —
    # the assistant should say so, not invent a product.
    expect_no_match: bool = False
    note: str = ""


TENANT_ID = "farmacia_carmen_sanjuan"

CASES: list[EvalCase] = [
    EvalCase(
        id="eye_puffiness",
        query="I need something for dark under-eye circles and puffiness",
        expected_products=["Flash Eye Contour Serum 15ml"],
        note="Only eye-contour product in the catalog ('Puffiness and bluish dark circles').",
    ),
    EvalCase(
        id="oily_pores_salicylic",
        query="My skin is oily and I want to reduce shine and minimize pores, ideally with salicylic acid",
        expected_products=["AHA/BHA Exfoliating Serum 30ml"],
        note="Only product with salicylic acid ('2% salicylic acid (BHA)... unclogs pores').",
    ),
    EvalCase(
        id="retinol_beginner_sensitive",
        query="Looking for a gentle retinol serum for beginners, my skin is sensitive",
        expected_products=["Tinolvital Serum 30ml"],
        note="Explicitly 'including sensitive' + 'Ideal for beginners in retinol' in the catalog copy.",
    ),
    EvalCase(
        id="pregnancy_safe_melasma",
        query="I'm pregnant and have melasma spots, what depigmenting product is safe to use?",
        expected_products=["Clear Azelaic Gel Cream 30ml"],
        note="Only depigmenting product explicitly labeled 'Safe during pregnancy/breastfeeding'.",
    ),
    EvalCase(
        id="vitamin_c_under_budget",
        query="I want a vitamin C serum, budget under 30 euros",
        expected_products=["Vital C Cream 30ml"],
        note="Vital C Serum is 49.90EUR (over budget); Vital C Cream is 25.90EUR and shares the vitamin C positioning. "
        "Tests that the deterministic price prefilter (parse_price -> (0, 30)) actually excludes the serum.",
    ),
    EvalCase(
        id="sunscreen_price_range",
        query="Recommend a facial sunscreen with SPF for daily use, budget 10 to 20 euros",
        expected_products=["SPF 50+ Sunscreen Cream"],
        note="Only SPF product in range (16.50EUR); the other sun product (Vitamin D Urban SPF30 Serum, 29.90EUR) is out of range.",
    ),
    EvalCase(
        id="neck_decollete_firming",
        query="I want a firming neck and décolleté cream for sagging skin",
        expected_products=["DMAE Lift 10 Cream 50ml"],
        note="Explicitly 'Specific care for neck/décolleté' in the catalog copy.",
    ),
    EvalCase(
        id="sensitive_eye_makeup_remover",
        query="What can I use to gently remove waterproof makeup around sensitive eyes?",
        expected_products=["Cleansing Oil 150ml"],
        note="Explicitly 'Makeup remover for sensitive eyes' + removes waterproof makeup.",
    ),
    EvalCase(
        id="out_of_catalog_hair_care",
        query="Do you sell hair dye or shampoo?",
        expect_no_match=True,
        note="The catalog has zero hair-care products (skincare only) -- the assistant must not invent one.",
    ),
]
