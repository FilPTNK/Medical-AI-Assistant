from openai import OpenAI
import config
from typing import List, Dict, Any

def generate_answer(query: str, context_chunks: List[Dict[str, Any]], custom_api_key: str = "") -> str:
    """
    Calls the DeepSeek API (using OpenAI client) to generate an answer
    based on the provided document contexts.
    """
    # Use custom key if provided, otherwise config key
    api_key = custom_api_key if custom_api_key else config.DEEPSEEK_API_KEY

    if not api_key:
        return (
            "DeepSeek API key is not configured. "
            "Please click the 'Settings' gear in the top right to configure your API key, "
            "or add it to your `.env` file in the project folder."
        )

    # Format the context text for the model
    context_str = ""
    for idx, chunk in enumerate(context_chunks):
        context_str += f"[{idx+1}] Source: {chunk['doc_name']}, Page: {chunk['page_num']}\n"
        context_str += f"Content: {chunk['text']}\n\n"

    system_prompt = (
        "You are a professional, highly precise Medical Assistant RAG (Retrieval-Augmented Generation) system.\n"
        "Your role is to assist doctors in finding information in medical books/guidelines they have uploaded.\n"
        "Analyze the provided medical context fragments and answer the user's question accurately.\n\n"
        "Rules:\n"
        "1. Answer ONLY using the facts from the provided context. Do not extrapolate or introduce outside medical information.\n"
        "2. Cite the source document and page number in your response when referencing specific facts (e.g. 'According to [Book, Page 12]...').\n"
        "3. If the answer cannot be found or inferred from the provided context, state: 'I could not find the information in the uploaded books. Please verify if you have uploaded the correct document.'\n"
        "4. Maintain a clear, objective, and professional medical tone."
    )

    user_prompt = f"Context:\n{context_str}\nQuestion: {query}\n\nAnswer:"

    try:
        # Initialize OpenAI client with DeepSeek credentials
        client = OpenAI(
            api_key=api_key,
            base_url=config.DEEPSEEK_API_URL
        )

        response = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,  # Low temperature for factuality
            max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error calling DeepSeek API: {e}")
        return f"Error calling DeepSeek API: {str(e)}\n\n(Please check your connection and DEEPSEEK_API_KEY settings in .env)"
