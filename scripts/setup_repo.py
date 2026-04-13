"""
setup_repo.py
-------------
One-time helper that prints the recommended GitHub repository topics
for MoneyMap AI. Run this after pushing to GitHub, then paste the
topics into: GitHub repo → ⚙️ (gear next to About) → Topics.
"""


def main() -> None:
    topics = [
        "finance",
        "monte-carlo-simulation",
        "streamlit",
        "data-science",
        "portfolio-analysis",
        "python",
        "financial-planning",
        "risk-analysis",
        "scenario-analysis",
        "macroeconomics",
    ]

    print(
        "Add these topics to your GitHub repo via Settings > Topics:\n"
        + ", ".join(topics)
    )


if __name__ == "__main__":
    main()
