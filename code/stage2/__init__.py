"""Stage 2 — Reading the claim.

Extract the genuine claim from the user_claim transcript into the SAME enums
Stage 1 emits (code/vocab.py), so Stage 3 reconciles by string match. The claim
owns neither image-usability nor verdict fields — ClaimRecord is a subset.
"""
