from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text as sql_text
from app.database import get_db
from app.models import Document, Embedding
from app.auth.dependencies import get_current_user
from app.ai_model.ai import generate_summary, generate_embedding
from app.models import User
from app.cache import get_cache, set_cache, generate_cache_key, delete_cache_pattern
from fastapi import Query
from sqlalchemy.exc import SQLAlchemyError
import fitz  # PyMuPDF
import docx2txt
import tempfile
import os

router = APIRouter(prefix="/documents", tags=["Documents"])


#  Background Task — process summarization + embedding

def process_document_background(doc_id: int, text: str, db_session_maker):
    """Background task to generate summary and embedding for a document"""
    db = db_session_maker()
    try:
        print(f"[Background Task] Starting processing for document ID: {doc_id}")
        
        # 1️ Generate summary
        print(f"[Background Task] Generating summary for document ID: {doc_id}")
        try:
            summary = generate_summary(text)
            print(f"[Background Task] Summary generated successfully for document ID: {doc_id}, length: {len(summary) if summary else 0}")
        except Exception as summary_error:
            print(f"[Background Task] ERROR generating summary for document ID {doc_id}: {summary_error}")
            raise Exception(f"Summary generation failed: {str(summary_error)}")

        # 2️ Generate embedding
        print(f"[Background Task] Generating embedding for document ID: {doc_id}")
        try:
            embedding_vector = generate_embedding(text)
            print(f"[Background Task] Embedding generated successfully for document ID: {doc_id}, dimensions: {len(embedding_vector) if embedding_vector else 0}")
        except Exception as embedding_error:
            print(f"[Background Task] ERROR generating embedding for document ID {doc_id}: {embedding_error}")
            raise Exception(f"Embedding generation failed: {str(embedding_error)}")

        # 3️ Update document record
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            print(f"[Background Task] ERROR: Document ID {doc_id} not found in database")
            return
            
        doc.summary = summary
        doc.status = "completed"
        db.commit()
        print(f"[Background Task] Document ID {doc_id} updated with summary")
        
        # Clear document cache when document is updated
        from app.cache import delete_cache_pattern
        delete_cache_pattern(f"document:*{doc_id}*")

        # 4️ Save embedding
        try:
            embedding_entry = Embedding(document_id=doc.id, embedding=embedding_vector)
            db.add(embedding_entry)
            db.commit()
            print(f"[Background Task] Embedding saved for document ID: {doc_id}")
            
            # Clear search cache when new embedding is saved (new embeddings may affect search results)
            delete_cache_pattern("search:*")
        except Exception as embedding_save_error:
            print(f"[Background Task] ERROR saving embedding for document ID {doc_id}: {embedding_save_error}")
            db.rollback()
            # Don't fail the whole task if embedding save fails, summary is more important
            doc.status = f"completed (embedding save failed: {str(embedding_save_error)})"
            db.commit()

    except Exception as e:
        print(f"[Background Task] CRITICAL ERROR processing document ID {doc_id}: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        try:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if doc:
                error_msg = f"failed: {type(e).__name__}: {str(e)}"
                # Truncate error message if too long
                if len(error_msg) > 500:
                    error_msg = error_msg[:497] + "..."
                doc.status = error_msg
                db.commit()
                print(f"[Background Task] Document ID {doc_id} status updated to failed")
        except Exception as db_error:
            print(f"[Background Task] ERROR updating document status: {db_error}")
    finally:
        try:
            db.close()
        except:
            pass
        print(f"[Background Task] Completed processing for document ID: {doc_id}")


#  Upload Document Endpoint

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    #  Validate file presence
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")

    filename = file.filename
    ext = filename.split(".")[-1].lower()

    #  Validate file type
    if ext not in ["pdf", "docx", "txt"]:
        raise HTTPException(status_code=400, detail="Unsupported file format")

    text = ""

    try:
        #  Read content safely based on file type
        if ext == "pdf":
            content = await file.read()
            if not content:
                raise HTTPException(status_code=400, detail="Uploaded PDF is empty")

            pdf = fitz.open(stream=content, filetype="pdf")
            for page in pdf:
                text += page.get_text()
            pdf.close()

        elif ext == "docx":
            with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
                tmp.write(await file.read())
                tmp_path = tmp.name
            try:
                text = docx2txt.process(tmp_path)
            finally:
                os.remove(tmp_path)

        else:  # TXT
            content = await file.read()
            if not content:
                raise HTTPException(status_code=400, detail="Uploaded text file is empty")
            text = content.decode("utf-8")

    except HTTPException:
        raise  # Re-raise handled HTTP errors

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading document: {str(e)}")

    #  Ensure text is not empty
    if not text.strip():
        raise HTTPException(status_code=400, detail="Empty or unreadable document")

    #  Save to database safely
    try:
        doc = Document(
            user_id=current_user.id,
            filename=filename,
            file_type=ext,
            content=text,
            status="processing",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
    except SQLAlchemyError as db_err:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Database error while saving document: {str(db_err)}",
        )

    #  Queue background processing safely
    try:
        from app.database import SessionLocal
        background_tasks.add_task(process_document_background, doc.id, text, SessionLocal)
    except Exception as bg_err:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start background processing: {str(bg_err)}",
        )

    #  Final response
    return {
        "message": "Document uploaded successfully. Summary and embedding are being processed.",
        "document_id": doc.id,
        "status": "processing",
    }

#  Search Documents Endpoint

@router.get("/search")
def semantic_search(
    query: str = Query(..., description="Search text to find similar documents"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Search for documents semantically similar to the query.
    Requires JWT token (user must be logged in).
    Results are cached for repeated queries.
    """
    try:
        #  Validate query
        if not query.strip():
            raise HTTPException(status_code=400, detail="Query cannot be empty")

        # Generate cache key for this query
        cache_key = generate_cache_key("search", query=query.strip().lower())
        
        # Try to get from cache
        cached_result = get_cache(cache_key)
        if cached_result is not None:
            return cached_result

        #  Generate query embedding
        query_embedding = generate_embedding(query)
        if not query_embedding or len(query_embedding) == 0:
            raise HTTPException(status_code=500, detail="Failed to generate query embedding")

        # Convert to PostgreSQL vector format for pgvector
        query_vector_str = "[" + ",".join(map(str, query_embedding)) + "]"

        #  Perform semantic similarity search in PostgreSQL
        sql = sql_text("""
            SELECT d.id, d.filename, d.summary, u.username,
                   (1 - (e.embedding <=> CAST(:query_vector AS vector))) AS similarity
            FROM documents d
            JOIN embeddings e ON d.id = e.document_id
            JOIN users u ON u.id = d.user_id
            ORDER BY e.embedding <=> CAST(:query_vector AS vector)
            LIMIT 10;
        """)

        results = db.execute(sql, {"query_vector": query_vector_str}).fetchall()

        if not results:
            response = {"message": "No results found", "results": []}
            # Cache empty results with shorter TTL (5 minutes)
            set_cache(cache_key, response, ttl=300)
            return response

        #  Filter and format results (only show good matches)
        filtered_results = [
            {
                "id": r.id,
                "filename": r.filename,
                "summary": r.summary,
                "username": r.username,
                "similarity": round(float(r.similarity), 4)
            }
            for r in results if float(r.similarity) > 0.2
        ]

        if not filtered_results:
            response = {"message": "No relevant results found", "results": []}
            # Cache empty results with shorter TTL (5 minutes)
            set_cache(cache_key, response, ttl=300)
            return response

        response = {"results": filtered_results}
        # Cache successful results (default TTL from settings)
        set_cache(cache_key, response)
        return response

    except HTTPException:
        raise
    except Exception as e:
        print(f" Error during semantic search: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")


#  Get Document by ID

@router.get("/{document_id}")
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        #  Validate input
        if document_id <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid document ID. Must be a positive integer."
            )

        # Generate cache key (include user_id for access control)
        cache_key = generate_cache_key("document", document_id=document_id, user_id=current_user.id)

        # Try to get from cache
        cached_result = get_cache(cache_key)
        if cached_result is not None:
            return cached_result

        #  Fetch document
        doc = db.query(Document).filter(Document.id == document_id).first()

        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document with ID {document_id} not found."
            )

        #  Restrict access: Only owner or admin can view
        if doc.user_id != current_user.id and current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to access this document."
            )

        #  Return structured response
        response = {
            "id": doc.id,
            "filename": doc.filename,
            "summary": doc.summary or "Summary not available yet.",
            "status": doc.status or ("completed" if doc.summary else "processing"),
            "uploaded_by": current_user.username if doc.user_id == current_user.id else doc.owner.username,
        }
        
        # Cache document response (15 minutes TTL for document data)
        set_cache(cache_key, response, ttl=900)
        return response

    except HTTPException:
        raise

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )