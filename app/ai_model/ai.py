# app/ai_model/ai.py
from transformers import pipeline
from sentence_transformers import SentenceTransformer
import nltk
import os
import hashlib
from functools import lru_cache

# Set NLTK data path to use cached volume if available
nltk_data_path = os.environ.get('NLTK_DATA', '/root/nltk_data')
os.environ['NLTK_DATA'] = nltk_data_path

# Download required NLTK data resources
def download_nltk_resources():
    """Download required NLTK resources if not already present"""
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        print("Downloading NLTK punkt tokenizer...")
        nltk.download("punkt", quiet=True)
    
    try:
        nltk.data.find('tokenizers/punkt_tab')
    except LookupError:
        print("Downloading NLTK punkt_tab tokenizer...")
        nltk.download("punkt_tab", quiet=True)

# Download NLTK resources on module import
download_nltk_resources()

# Set environment variables for HuggingFace to increase timeout and enable caching
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "300")  # 5 minutes timeout
os.environ.setdefault("TRANSFORMERS_OFFLINE", "0")  # Allow online downloads

#  Cached Model Loaders

@lru_cache(maxsize=1)
def get_summarizer():
    # Use a stronger summarization model with optimized settings
    print("Loading summarization model (first time may take a while)...")
    try:
        return pipeline(
            "summarization",
            model="sshleifer/distilbart-cnn-12-6",
            tokenizer="sshleifer/distilbart-cnn-12-6",
            device=-1,  # Use CPU (set to 0 for GPU if available)
            framework="pt"  # Use PyTorch for better performance
        )
    except Exception as e:
        print(f"Error loading summarization model: {e}")
        raise

@lru_cache(maxsize=1)
def get_embedding_model():
    print("Loading embedding model (first time may take a while)...")
    try:
        return SentenceTransformer("all-MiniLM-L6-v2")
    except Exception as e:
        print(f"Error loading embedding model: {e}")
        raise

# Lazy loading - models will be loaded on first use

# Optimized settings for faster summarization
MAX_INPUT_WORDS = 3000  # Reduced from 5000 for faster processing
CHUNK_MAX_WORDS = 300   # Reduced chunk size for faster processing (was 400)


#  Chunk Long Text (Optimized)

def chunk_text(text, max_words=300):
    """Chunk text into smaller pieces for faster summarization."""
    sentences = nltk.sent_tokenize(text)
    chunks, current_chunk = [], []
    current_word_count = 0
    
    for sentence in sentences:
        sentence_words = len(sentence.split())
        # Add sentence if it fits, otherwise start new chunk
        if current_word_count + sentence_words <= max_words:
            current_chunk.append(sentence)
            current_word_count += sentence_words
        else:
            if current_chunk:
                chunks.append(" ".join(current_chunk))
            current_chunk = [sentence]
            current_word_count = sentence_words
    
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    return chunks


def get_text_hash(text: str) -> str:
    """Generate a hash for text to use as cache key."""
    # Normalize text (remove extra whitespace)
    normalized = " ".join(text.strip().split())
    return hashlib.md5(normalized.encode()).hexdigest()


#  Generate Summary (Optimized)

def generate_summary(text: str, use_cache: bool = True) -> str:
    """
    Generate an abstractive summary with chunked processing.
    Optimized for faster processing with caching support.
    """
    if not text.strip():
        return ""

    # Try to get from cache first (if enabled and cache available)
    if use_cache:
        try:
            from app.cache import get_cache, set_cache, generate_cache_key
            text_hash = get_text_hash(text)
            cache_key = generate_cache_key("summary", text_hash=text_hash)
            cached_summary = get_cache(cache_key)
            if cached_summary:
                print(" Summary retrieved from cache")
                return cached_summary
        except Exception as e:
            # If cache fails, continue with normal generation
            print(f" Cache check failed, generating new summary: {e}")

    # Limit input size for faster processing
    words = text.split()
    if len(words) > MAX_INPUT_WORDS:
        text = " ".join(words[:MAX_INPUT_WORDS])
        print(f" Text truncated to {MAX_INPUT_WORDS} words for faster processing")

    chunks = chunk_text(text, max_words=CHUNK_MAX_WORDS)
    
    # Skip summarization if very short
    if len(chunks) == 0:
        return text[:500]  # Return first 500 chars if no chunks
    
    summaries = []

    # Get summarizer lazily (loads on first use)
    summarizer = get_summarizer()
    
    # Process chunks with optimized settings
    for i, chunk in enumerate(chunks):
        chunk_words = len(chunk.split())
        
        # For very short chunks, include directly (skip summarization)
        if chunk_words < 30:
            summaries.append(chunk)
            continue
        
        try:
            # Optimized summarization parameters for speed
            summary_result = summarizer(
                chunk,
                max_length=min(150, max(60, chunk_words // 3)),  # Adaptive max length
                min_length=30,  # Reduced from 40
                do_sample=False,  # Greedy decoding (faster)
                num_beams=4,  # Reduced beams for faster inference (default is 5)
                early_stopping=True,  # Stop early when possible
                truncation=True,  # Truncate if needed
                no_repeat_ngram_size=2  # Avoid repetition
            )
            summaries.append(summary_result[0]["summary_text"])
        except Exception as e:
            print(f" Summarization failed for chunk {i+1}/{len(chunks)}: {e}")
            # Fallback: use first part of chunk
            summaries.append(chunk[:200])

    final_summary = " ".join(summaries)

    # Final compression only if significantly long (reduced threshold)
    final_words = len(final_summary.split())
    if final_words > 250:  # Reduced from 300
        try:
            final_summary = summarizer(
                final_summary,
                max_length=200,  # Reduced from 250
                min_length=60,   # Reduced from 80
                do_sample=False,
                num_beams=4,
                early_stopping=True,
                truncation=True
            )[0]["summary_text"]
        except Exception as e:
            print(f" Final compression failed: {e}")
            # If compression fails, truncate to reasonable length
            final_summary = " ".join(final_summary.split()[:200])

    # Cache the result (if enabled)
    if use_cache:
        try:
            from app.cache import set_cache, generate_cache_key
            text_hash = get_text_hash(text)
            cache_key = generate_cache_key("summary", text_hash=text_hash)
            # Cache summaries for 24 hours (summaries don't change)
            set_cache(cache_key, final_summary, ttl=86400)
        except Exception as e:
            print(f" Failed to cache summary: {e}")

    return final_summary



#  Generate Embedding

def generate_embedding(text: str):
    """Create a semantic embedding vector."""
    # Get embedding model lazily (loads on first use)
    embedding_model = get_embedding_model()
    return embedding_model.encode(text).tolist()
