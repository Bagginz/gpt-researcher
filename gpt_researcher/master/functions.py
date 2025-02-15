import asyncio
from gpt_researcher.utils.llm import *
from gpt_researcher.scraper import Scraper
from gpt_researcher.master.prompts import *
from gpt_researcher.utils.google_pub import PublishManager
import json


def get_retriever(retriever):
    """
    Gets the retriever
    Args:
        retriever: retriever name

    Returns:
        retriever: Retriever class

    """
    match retriever:
        case "tavily":
            from gpt_researcher.retrievers import TavilySearch
            retriever = TavilySearch
        case "tavily_news":
            from gpt_researcher.retrievers import TavilyNews
            retriever = TavilyNews
        case "google":
            from gpt_researcher.retrievers import GoogleSearch
            retriever = GoogleSearch
        case "searx":
            from gpt_researcher.retrievers import SearxSearch
            retriever = SearxSearch
        case "serpapi":
            raise NotImplementedError("SerpApiSearch is not fully implemented yet.")
            from gpt_researcher.retrievers import SerpApiSearch
            retriever = SerpApiSearch
        case "googleSerp":
            from gpt_researcher.retrievers import SerperSearch
            retriever = SerperSearch
        case "duckduckgo":
            from gpt_researcher.retrievers import Duckduckgo
            retriever = Duckduckgo
        case "BingSearch":
            from gpt_researcher.retrievers import BingSearch
            retriever = BingSearch

        case _:
            raise Exception("Retriever not found.")

    return retriever


async def choose_agent(query, cfg, message_type=None, user_id=None):
    """
    Chooses the agent automatically
    Args:
        query: original query
        cfg: Config

    Returns:
        agent: Agent name
        agent_role_prompt: Agent role prompt
    """
    try:
        response = await create_chat_completion(
            model=cfg.smart_llm_model,
            messages=[
                {"role": "system", "content": f"{auto_agent_instructions()}"},
                {"role": "user", "content": f"task: {query}"}],
            temperature=0,
            llm_provider=cfg.llm_provider,
            message_type=message_type,
            user_id=user_id
        )
        agent_dict = json.loads(response)
        return agent_dict["server"], agent_dict["agent_role_prompt"]
    except Exception as e:
        return "Default Agent", "You are an AI critical thinker research assistant. Your sole purpose is to write well written, critically acclaimed, objective and structured reports on given text."


async def get_sub_queries(query, agent_role_prompt, cfg, message_type=None, user_id=None):
    """
    Gets the sub queries
    Args:
        query: original query
        agent_role_prompt: agent role prompt
        cfg: Config

    Returns:
        sub_queries: List of sub queries

    """
    max_research_iterations = cfg.max_iterations if cfg.max_iterations else 1
    response = await create_chat_completion(
        model=cfg.smart_llm_model,
        messages=[
            {"role": "system", "content": f"{agent_role_prompt}"},
            {"role": "user", "content": generate_search_queries_prompt(query, max_iterations=max_research_iterations)}],
        temperature=0,
        llm_provider=cfg.llm_provider,
        message_type=message_type,
        user_id=user_id
    )
    sub_queries = json.loads(response)
    return sub_queries


def scrape_urls(urls, cfg=None):
    """
    Scrapes the urls
    Args:
        urls: List of urls
        cfg: Config (optional)

    Returns:
        text: str

    """
    content = []
    user_agent = cfg.user_agent if cfg else "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0"
    try:
        content = Scraper(urls, user_agent).run()
    except Exception as e:
        print(f"{Fore.RED}Error in scrape_urls: {e}{Style.RESET_ALL}")
    return content


async def summarize(query, content, agent_role_prompt, cfg, websocket=None, message_type=None, user_id=None):
    """
    Asynchronously summarizes a list of URLs.

    Args:
        query (str): The search query.
        content (list): List of dictionaries with 'url' and 'raw_content'.
        agent_role_prompt (str): The role prompt for the agent.
        cfg (object): Configuration object.

    Returns:
        list: A list of dictionaries with 'url' and 'summary'.
    """

    # Function to handle each summarization task for a chunk
    async def handle_task(url, chunk, message_type=None, user_id=None):
        summary = await summarize_url(query, chunk, agent_role_prompt, cfg)
        if summary:
            await stream_output("logs", f"🌐 Summarizing url: {url}", websocket, message_type, user_id)
            await stream_output("logs", f"📃 {summary}", websocket, message_type, user_id)
        return url, summary

    # Function to split raw content into chunks of 10,000 words
    def chunk_content(raw_content, chunk_size=10000):
        words = raw_content.split()
        for i in range(0, len(words), chunk_size):
            yield ' '.join(words[i:i+chunk_size])

    # Process each item one by one, but process chunks in parallel
    concatenated_summaries = []
    for item in content:
        url = item['url']
        raw_content = item['raw_content']

        # Create tasks for all chunks of the current URL
        chunk_tasks = [handle_task(url, chunk, message_type, user_id) for chunk in chunk_content(raw_content)]

        # Run chunk tasks concurrently
        chunk_summaries = await asyncio.gather(*chunk_tasks)

        # Aggregate and concatenate summaries for the current URL
        summaries = [summary for _, summary in chunk_summaries if summary]
        concatenated_summary = ' '.join(summaries)
        concatenated_summaries.append({'url': url, 'summary': concatenated_summary})

    return concatenated_summaries


async def summarize_url(query, raw_data, agent_role_prompt, cfg, message_type=None, user_id=None):
    """
    Summarizes the text
    Args:
        query:
        raw_data:
        agent_role_prompt:
        cfg:

    Returns:
        summary: str

    """
    summary = ""
    try:
        summary = await create_chat_completion(
            model=cfg.fast_llm_model,
            messages=[
                {"role": "system", "content": f"{agent_role_prompt}"},
                {"role": "user", "content": f"{generate_summary_prompt(query, raw_data)}"}],
            temperature=0,
            llm_provider=cfg.llm_provider,
            message_type=message_type,
            user_id=user_id
        )
    except Exception as e:
        print(f"{Fore.RED}Error in summarize: {e}{Style.RESET_ALL}")
    return summary



async def generate_report(query, context, agent_role_prompt, report_type, websocket, cfg, message_type=None, user_id=None):
    """
    generates the final report
    Args:
        query:
        context:
        agent_role_prompt:
        report_type:
        websocket:
        cfg:

    Returns:
        report:

    """
    generate_prompt = get_report_by_type(report_type)
    report = ""
    try:
        report = await create_chat_completion(
            model=cfg.smart_llm_model,
            messages=[
                {"role": "system", "content": f"{agent_role_prompt}"},
                {"role": "user", "content": f"{generate_prompt(query, context, cfg.report_format, cfg.total_words)}"}],
            temperature=0,
            llm_provider=cfg.llm_provider,
            stream=True,
            websocket=websocket,
            message_type=message_type,
            user_id=user_id
        )
        return report
    except Exception as e:
        print(f"{Fore.RED}Error in generate_report: {e}{Style.RESET_ALL}")
        return f"Error in generate_report: {e}{Style.RESET_ALL}"



async def stream_output(type, output, websocket=None, message_type=None, user_id=None, logging=True):
    """
    Streams output to the websocket
    Args:
        type:
        output:

    Returns:
        None
    """
    if not websocket or logging:
        print(output)

    if websocket:
        await websocket.send_json({"type": type, "output": output})

    if not websocket:
        publish_manager = PublishManager()
        publish_manager.publish_message({"type": type, "output": output, "message_type": message_type, "user_id": user_id })

