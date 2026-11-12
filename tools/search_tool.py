"""
tools/search_tool.py
====================================================================
Implements web search and scraping capabilities using DuckDuckGo.
Provides resilient fetching and concurrent article parsing.
====================================================================
"""

import concurrent.futures
import logging
import random
import re
import threading
import time
from datetime import datetime, timezone
from typing import List, Dict, Any

from bs4 import BeautifulSoup
from curl_cffi import requests
from ddgs import DDGS
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from config.config import SEARCH_MAX_RESULTS, SEARCH_TIMEOUT, DOMAIN_1, DOMAIN_2, DOMAIN_3
from langfuse import observe

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Lightweight lock to provide minimal staggering between concurrent subagent searches
_ddgs_lock = threading.Lock()


def _extract_pub_date(soup: BeautifulSoup) -> str:
    """
    Extracts the publication date from common HTML meta and time tags,
    standardizing it strictly to 'YYYY-MM-DD' without time or timezone components.

    Args:
        soup (BeautifulSoup): The parsed HTML content of the page.

    Returns:
        str: The extracted date in 'YYYY-MM-DD' format or 'Unknown' if not found.
    """
    meta_tags = [
        ('property', 'article:published_time'),
        ('property', 'og:article:published_time'),
        ('name', 'pubdate'),
        ('name', 'date'),
        ('name', 'dc.date'),
        ('name', 'creation_date')
    ]
    raw_date = None
    for attr, val in meta_tags:
        meta_date = soup.find('meta', attrs={attr: val})
        if meta_date and meta_date.get('content'):
            raw_date = meta_date.get('content').strip()
            break

    if not raw_date:
        time_tag = soup.find('time')
        if time_tag and time_tag.get('datetime'):
            raw_date = time_tag.get('datetime').strip()

    if raw_date:
        # Extract direct YYYY-MM-DD pattern if present
        date_match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", raw_date)
        if date_match:
            return date_match.group(0)
        # Fallback ISO parsing
        try:
            clean_date = raw_date.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_date)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return "Unknown"

    return "Unknown"


def _parse_date_for_sorting(date_str: str) -> datetime:
    """
    Converts a 'YYYY-MM-DD' date string into an offset-aware UTC datetime for sorting.

    Args:
        date_str (str): The date string to parse.

    Returns:
        datetime: An offset-aware UTC datetime object.
    """
    min_date_utc = datetime.min.replace(tzinfo=timezone.utc)
    if date_str == "Unknown" or not date_str:
        return min_date_utc
    try:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return min_date_utc


def _fetch_and_parse_article(
    session: requests.Session,
    url: str,
    fallback_snippet: str,
    timeout: int = SEARCH_TIMEOUT,
) -> Dict[str, str]:
    """
    Worker function to fetch and extract article body text and metadata concurrently.

    Args:
        session (requests.Session): The active HTTP session.
        url (str): The URL of the article to fetch.
        fallback_snippet (str): Snippet to use if fetching fails or content is empty.
        timeout (int): Request timeout in seconds.

    Returns:
        Dict[str, str]: A dictionary containing "content" and "pub_date".
    """
    try:
        response = session.get(url, timeout=timeout)
        if response.status_code != 200:
            return {
                "content": f"[HTTP {response.status_code}] Fallback Snippet: {fallback_snippet}",
                "pub_date": "Unknown",
            }
        soup = BeautifulSoup(response.content, 'html.parser')
        pub_date = _extract_pub_date(soup)
        for element in soup(["script", "style", "nav", "header", "footer"]):
            element.decompose()
        paragraphs = soup.find_all('p')
        extracted_text = "\n".join(
            p.get_text(separator=' ', strip=True)
            for p in paragraphs
            if len(p.get_text(strip=True)) > 15
        )
        if not extracted_text:
            return {
                "content": f"[Empty Content] Fallback Snippet: {fallback_snippet}",
                "pub_date": pub_date,
            }
        return {
            "content": extracted_text,
            "pub_date": pub_date,
        }
    except Exception as e:
        logging.info("Failed to fetch content for %s: %s", url, e)
        return {
            "content": f"[Connection Error] Fallback Snippet: {fallback_snippet}",
            "pub_date": "Unknown",
        }


@observe(name="DuckDuckGo_Search_Tool", as_type="tool")
def duckduckgo_search(
    query: str,
    max_results: int = SEARCH_MAX_RESULTS,
    domain: str = "",
) -> List[Dict[str, str]]:
    """
    Executes a web search on the target domain using DuckDuckGo HTML backend.
    Preserves configured domain paths while eliminating rate-limit penalties.

    Args:
        query (str): The search query.
        max_results (int): Maximum number of results to retrieve.
        domain (str): The target domain to restrict the search to.

    Returns:
        List[Dict[str, str]]: A list of sorted search results with titles, links, dates, and content.
    """
    # Clean only protocol and trailing slashes, preserving subpaths as configured
    clean_domain = domain.replace("https://", "").replace("http://", "").rstrip("/")
    search_query = f"{query} site:{clean_domain}" if clean_domain else query
    ddg_results = []

    # Minimal stagger between agents to prevent burst collision
    with _ddgs_lock:
        time.sleep(random.uniform(0.15, 0.30))
        try:
            # Primary attempt using the resilient 'html' backend
            ddg_results = list(DDGS().text(search_query, max_results=max_results, backend="html"))
        except Exception as e:
            logging.warning("HTML backend search failed for '%s': %s. Retrying with default backend...", search_query, e)
            try:
                # Graceful fallback to default backend if html parser encounters issues
                ddg_results = list(DDGS().text(search_query, max_results=max_results))
            except Exception as fallback_err:
                logging.error("Fallback search failed for '%s': %s", search_query, fallback_err)
                return []

    if not ddg_results:
        logging.warning("No search results found for query: '%s'", search_query)
        return []

    results = []
    with requests.Session(impersonate="chrome120") as session:
        session.headers.update({
            "Referer": "https://duckduckgo.com/",
            "Accept-Language": "en-US,en;q=0.9",
        })
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_results) as executor:
            future_to_item = {}
            for item in ddg_results:
                real_url = item.get("href", "")
                if not real_url:
                    continue
                fallback_snippet = item.get("body", "No snippet available")
                future = executor.submit(_fetch_and_parse_article, session, real_url, fallback_snippet)
                future_to_item[future] = item

            for future in concurrent.futures.as_completed(future_to_item):
                original_item = future_to_item[future]
                title = original_item.get("title", "No title")
                link = original_item.get("href", "")
                try:
                    data = future.result()
                    article_content = data["content"]
                    pub_date = data["pub_date"]
                except Exception as exc:
                    logging.info("Thread generated an exception for %s: %s", link, exc)
                    article_content = f"[Thread Error] Fallback Snippet: {original_item.get('body', '')}"
                    pub_date = "Unknown"
                results.append({
                    "title": title,
                    "link": link,
                    "pub_date": pub_date,
                    "content": article_content,
                })

    results.sort(key=lambda x: _parse_date_for_sorting(x["pub_date"]), reverse=True)
    return results


def before_tool(tool: BaseTool, args: Dict[str, Any], tool_context: ToolContext) -> None:
    """
    Injects the corresponding domain directly into tool arguments for each subagent.

    Args:
        tool (BaseTool): The tool being called.
        args (Dict[str, Any]): The arguments passed to the tool.
        tool_context (ToolContext): The ADK tool context.

    Returns:
        None
    """
    agent_name = tool_context.agent_name
    query = args.get("query", "")

    if agent_name == "subagent_1":
        args["domain"] = DOMAIN_1
        tool_context.state["query_subagent_1"] = query
    elif agent_name == "subagent_2":
        args["domain"] = DOMAIN_2
        tool_context.state["query_subagent_2"] = query
    elif agent_name == "subagent_3":
        args["domain"] = DOMAIN_3
        tool_context.state["query_subagent_3"] = query

    logging.info(
        "[%s] 🛠️ Callback Before Tool Call: %s | Injected Domain: %s | Query: %s",
        agent_name,
        getattr(tool, 'name', 'tool'),
        args.get("domain"),
        query,
    )
    return None


def after_tool(
    tool: BaseTool,
    args: Dict[str, Any],
    tool_context: ToolContext,
    tool_response: Any,
) -> None:
    """
    Saves the retrieved tool response to the agent context state.

    Args:
        tool (BaseTool): The tool that was executed.
        args (Dict[str, Any]): The arguments used for the tool call.
        tool_context (ToolContext): The ADK tool context.
        tool_response (Any): The output returned by the tool.

    Returns:
        None
    """
    agent_name = tool_context.agent_name
    tool_context.actions.skip_summarization = True
    if agent_name == "subagent_1":
        tool_context.state["result_tool_subagent_1"] = tool_response
    elif agent_name == "subagent_2":
        tool_context.state["result_tool_subagent_2"] = tool_response
    elif agent_name == "subagent_3":
        tool_context.state["result_tool_subagent_3"] = tool_response

    logging.info(
        "[%s] 📋 Callback After Tool Call: %s (Articles fetched: %d)",
        agent_name,
        getattr(tool, 'name', 'tool'),
        len(tool_response) if isinstance(tool_response, list) else 0,
    )
    return None