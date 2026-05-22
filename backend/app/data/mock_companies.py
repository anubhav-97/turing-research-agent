"""Mock company research data, extended beyond the spec's two examples.

The keys are normalised lower-case so lookup is case-insensitive and tolerant
of common ticker/aka variants (e.g. "tesla" matches "Tesla Inc.").
"""

from __future__ import annotations

MOCK_RESEARCH: dict[str, dict[str, str]] = {
    "Apple Inc.": {
        "recent_news": "Launched Vision Pro spatial computer; expanding services revenue with ad-supported tier discussions.",
        "stock_info": "Trading near $195, up ~45% YTD; market cap ~$3.0T.",
        "key_developments": "AI integration across product line (Apple Intelligence); on-device LLM features; Vision OS app ecosystem growth.",
    },
    "Tesla": {
        "recent_news": "Cybertruck deliveries ramping up; price cuts across Model 3/Y to defend share against BYD.",
        "stock_info": "Trading near $242, volatile quarter; ~30% drawdown then partial recovery.",
        "key_developments": "FSD v12 end-to-end neural net rollout; Megapack energy-storage backlog at record levels.",
    },
    "NVIDIA": {
        "recent_news": "Blackwell B200 GPU shipments accelerating; data-center revenue up ~400% YoY.",
        "stock_info": "Trading near $880, up >180% YTD; briefly the world's most valuable company.",
        "key_developments": "CUDA moat deepening; Omniverse adoption in automotive and robotics; sovereign-AI deals with multiple governments.",
    },
    "Microsoft": {
        "recent_news": "Copilot for Microsoft 365 rolling out broadly; OpenAI partnership extended.",
        "stock_info": "Trading near $415, up ~25% YTD; market cap ~$3.1T.",
        "key_developments": "Azure AI workloads driving infra capex; Phi-3 small-model line gaining traction; gaming consolidation (Activision) closed.",
    },
    "Google": {
        "recent_news": "Gemini 1.5 Pro launched with 1M-token context; AI Overviews integrated in Search.",
        "stock_info": "Trading near $175 (Alphabet); up ~30% YTD.",
        "key_developments": "DeepMind merger paying off; TPU v5 deployments; antitrust pressure on default-search deals continues.",
    },
    "Amazon": {
        "recent_news": "AWS Bedrock GA with broad model catalogue; Anthropic strategic investment expanded.",
        "stock_info": "Trading near $185, up ~20% YTD.",
        "key_developments": "Trainium2 chips entering production; retail margin recovery; Project Kuiper satellite launches scheduled.",
    },
}


# Common aliases → canonical key in MOCK_RESEARCH
ALIASES: dict[str, str] = {
    "apple": "Apple Inc.",
    "aapl": "Apple Inc.",
    "tesla": "Tesla",
    "tsla": "Tesla",
    "nvidia": "NVIDIA",
    "nvda": "NVIDIA",
    "microsoft": "Microsoft",
    "msft": "Microsoft",
    "google": "Google",
    "alphabet": "Google",
    "googl": "Google",
    "amazon": "Amazon",
    "amzn": "Amazon",
}


def lookup(company: str) -> dict[str, str] | None:
    """Case-insensitive, alias-aware lookup. Returns None when unknown."""
    if not company:
        return None
    key = company.strip().lower()
    canonical = ALIASES.get(key)
    if canonical:
        return MOCK_RESEARCH[canonical] | {"company": canonical}
    # Try direct case-insensitive match against the canonical keys
    for k, v in MOCK_RESEARCH.items():
        if k.lower() == key:
            return v | {"company": k}
    return None
