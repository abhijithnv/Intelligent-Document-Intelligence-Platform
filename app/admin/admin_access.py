from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.database import get_db
from app.auth.dependencies import admin_required
from app.models import User, Document

router = APIRouter(prefix="/admin", tags=["Admin"])

#  GET ALL SUMMARIES (Admin Only)
@router.get("/summaries")
def get_all_summaries(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_required)
):
    try:
        summaries = db.query(Document).join(User).all()

        if not summaries:
            return {"message": "No summaries found", "summaries": []}

        result = []
        for doc in summaries:
            result.append({
                "id": doc.id,
                "filename": doc.filename,
                "summary": doc.summary or "No summary available.",
                "username": doc.owner.username if hasattr(doc, "owner") and doc.owner else "Unknown"
            })

        return {"summaries": result}

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )



#  DELETE SUMMARY (Admin Only)

@router.delete("/summaries/{summary_id}")
def delete_summary(
    summary_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_required)
):
    try:
        # Validate ID
        if summary_id <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid summary ID. Must be a positive integer."
            )

        # Find summary
        summary = db.query(Document).filter(Document.id == summary_id).first()
        if not summary:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Summary with ID {summary_id} not found."
            )

        db.delete(summary)
        db.commit()

        return {"message": f"Summary (ID: {summary_id}) deleted successfully."}

    except HTTPException:
        raise

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )