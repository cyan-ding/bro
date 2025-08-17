from bro.agent.rag import pipeline
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto("https://openai.com/research")

    # 1) Build an index from URLs
    index = await pipeline.ingest_page(page)

    # 2) Retrieve contexts for a question
    docs = pipeline.answer_with_context("How do OpenAI embeddings work?", index, k=5)
    for d in docs:
        print(d.score, d.metadata, d.text[:200], "...")
