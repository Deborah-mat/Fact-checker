from mcp.server.fastmcp import FastMCP
from pygooglenews import GoogleNews
from newspaper import Article
from newspaper.article import ArticleException
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from typing import List, Dict
import requests
import time
import pywhatkit
import xml.etree.ElementTree as ET


mcp = FastMCP("news-checker")

@mcp.tool()
def search_news(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    """
    Search recent news articles from Google News.
    
    IMPORTANT: This is the ONLY allowed search method for fact-checking.
    Do NOT use general web search or Google Search.
    """
    print(f"🔍 TOOL CALLED: search_news with query: '{query}'")  # Debug line
    
    try:
        # Use Google News RSS feed
        rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        response = requests.get(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        
        # Parse RSS
        root = ET.fromstring(response.content)
        items = root.findall('.//item')
        
        print(f"✅ Found {len(items)} results")  # Debug line
        
        results = []
        for item in items[:max_results]:
            title = item.find('title').text if item.find('title') is not None else ""
            link = item.find('link').text if item.find('link') is not None else ""
            pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ""
            source = item.find('source').text if item.find('source') is not None else ""
            
            results.append({
                "title": title,
                "link": link,
                "published": pub_date,
                "source": source
            })
        
        return results
    except Exception as e:
        print(f"Error: {str(e)}")
        return []



# TOOL 2 — Fact Checker


@mcp.tool()
def fact_check_claim(claim: str, articles: list[dict]) -> dict:
    """
    Fact-check a claim using the content of news articles and extract context for the agent.

    Parameters
    ----------
    claim : str
        Claim to verify.
    articles : list[dict]
        Articles returned by search_news.

    Returns
    -------
    verdict, explanation, sources, contexts
    """

    supporting = []
    contradicting = []
    unclear = []
    contexts = []  # Store extracted context from articles

    claim_words = claim.lower().split()

    for article in articles:

        try:
            # --- READ ARTICLE CONTENT ---
            a = Article(article["link"])
            a.download()
            a.parse()

            title = article["title"]
            source = article.get("source", "")
            published = article.get("published", "")
            text = a.text.lower()
            
            # --- EXTRACT RELEVANT CONTEXT ---
            # Get sentences containing the claim words
            sentences = a.text.split('. ')
            relevant_sentences = []
            
            for sentence in sentences:
                sentence_lower = sentence.lower()
                if any(word in sentence_lower for word in claim_words):
                    relevant_sentences.append(sentence.strip())
            
            # Limit to 3 sentences per article to avoid too much text
            if len(relevant_sentences) > 3:
                relevant_sentences = relevant_sentences[:3]
            
            # Create context summary
            context_summary = {
                "title": title,
                "source": source,
                "published": published,
                "link": article["link"],
                "relevant_excerpts": relevant_sentences,
                "full_text_preview": text[:500] + "..." if len(text) > 500 else text
            }
            
            contexts.append(context_summary)

            # --- IMPROVED FACT CHECKING WITH ANALYSIS ---
            # Check word presence and proximity
            text_words = text.split()
            
            # Calculate relevance score
            relevance_score = 0
            words_found = 0
            
            for word in claim_words:
                if word in text:
                    words_found += 1
                    # Check if word appears in a relevant sentence
                    for sentence in sentences:
                        if word in sentence.lower():
                            relevance_score += 2
                            break
            
            # Calculate word ratio found
            word_ratio = words_found / len(claim_words) if claim_words else 0
            
            # Determine support based on nuanced analysis
            if word_ratio > 0.7 and relevance_score > 5:
                supporting.append({
                    "link": article["link"],
                    "title": title,
                    "relevance_score": relevance_score
                })
            elif word_ratio > 0.3:
                contradicting.append({
                    "link": article["link"],
                    "title": title,
                    "relevance_score": relevance_score
                })
            else:
                unclear.append({
                    "link": article["link"],
                    "title": title,
                    "relevance_score": relevance_score
                })

        except Exception as e:
            print(f"Error processing article {article.get('link', 'unknown')}: {str(e)}")
            continue

    # --- VERDICT WITH DETAILED EXPLANATION ---
    supporting_count = len(supporting)
    contradicting_count = len(contradicting)
    unclear_count = len(unclear)
    
    if supporting_count > contradicting_count:
        verdict = "LIKELY TRUE"
        confidence = supporting_count / (supporting_count + contradicting_count + unclear_count) * 100 if (supporting_count + contradicting_count + unclear_count) > 0 else 0
        explanation = f"The claim is likely true with a confidence level of {confidence:.1f}%. {supporting_count} source(s) support it, {contradicting_count} contradict it."
        
    elif contradicting_count > supporting_count:
        verdict = "LIKELY FALSE"
        confidence = contradicting_count / (supporting_count + contradicting_count + unclear_count) * 100 if (supporting_count + contradicting_count + unclear_count) > 0 else 0
        explanation = f"The claim is likely false with a confidence level of {confidence:.1f}%. {contradicting_count} source(s) contradict it, {supporting_count} support it."
        
    else:
        verdict = "UNCLEAR"
        explanation = f"Sources are divided or insufficient. {supporting_count} source(s) support, {contradicting_count} contradict, and {unclear_count} are unclear."

    return {
        "claim": claim,
        "verdict": verdict,
        "explanation": explanation,
        "summary": {
            "supporting_count": supporting_count,
            "contradicting_count": contradicting_count,
            "unclear_count": unclear_count,
            "total_articles": len(articles)
        },
        "supporting_sources": supporting,
        "contradicting_sources": contradicting,
        "unclear_sources": unclear,
        "contexts": contexts,  # Extracted context for the agent
        "analysis_timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }




# TOOL 3 — SEND Whatsapp message

@mcp.tool()
def send_whatsapp_message(phone_number: str, message: str) -> None:
    """
    Sends a text message via WhatsApp Web.

    Args:
        phone_number (str): Phone number in international format (e.g. +33612345678)
        message (str): Message text to send
    """

    if not isinstance(phone_number, str) or not phone_number.startswith("+"):
        raise ValueError("Phone number must be in international format (e.g. +33612345678)")

    if not isinstance(message, str) or not message.strip():
        raise ValueError("Message is empty or invalid")

    print("Sending WhatsApp message...")

    pywhatkit.sendwhatmsg_instantly(
        phone_no=phone_number,
        message=message.strip(),
        wait_time=15,
        tab_close=True,
        close_time=3
    )

    time.sleep(2)
    print("Message sent successfully.")

 

def main():
    print("Starting Fact Check MCP Agent...")

    mcp.run(transport="stdio")  

if __name__ == "__main__":
    main()