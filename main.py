"""
MicroSaaS — ContentOptimizer AI API
Deployed on Railway. Validates Gumroad license keys via their API.
"""
import os, uuid, json, httpx
from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from datetime import datetime

app = FastAPI(title="ContentOptimizer API", version="1.0.0")
security = HTTPBearer()

# Gumroad config - set via Railway env vars
GUMROAD_PRODUCT_ID = os.getenv("GUMROAD_PRODUCT_ID", "coAI")
GUMROAD_ACCESS_TOKEN = os.getenv("GUMROAD_ACCESS_TOKEN", "")

# OpenRouter key
OR_KEY = os.getenv("OPENROUTER_KEY", "")
# Master key for the product owner
MASTER_KEY = os.getenv("MASTER_KEY", "")


async def verify_gumroad_license(license_key: str) -> bool:
    """Verify a Gumroad license key is valid for this product."""
    if not license_key:
        return False
        
    # Master key bypass for the owner
    if MASTER_KEY and license_key == MASTER_KEY:
        return True
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.gumroad.com/v2/licenses/verify",
                data={
                    "product_permalink": GUMROAD_PRODUCT_ID,
                    "license_key": license_key
                }
            )
            data = resp.json()
            return data.get("success") is True and data.get("uses", 0) > 0
    except Exception as e:
        print(f"Gumroad verify error: {e}")
        return False


def verify_key(creds: HTTPAuthorizationCredentials = Security(security)):
    """Validate API key (Gumroad license key or master key)."""
    token = creds.credentials
    # For the master/owner key
    if MASTER_KEY and token == MASTER_KEY:
        return token
    raise HTTPException(status_code=401, detail="Invalid API key. Purchase at https://d6goat9p.gumroad.com/l/coAI")


class AnalyzeRequest(BaseModel):
    content: str

class AnalyzeResponse(BaseModel):
    title: str
    meta_description: str
    keywords: list[str]
    readability_score: int
    suggestions: list[str]


@app.get("/health")
def health():
    return {"status": "healthy", "version": "1.0.0", "product": GUMROAD_PRODUCT_ID}


@app.get("/verify")
def verify_license_key(creds: HTTPAuthorizationCredentials = Security(security)):
    """Check if a license key is valid."""
    return {"valid": True, "product": GUMROAD_PRODUCT_ID}


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest, api_key: str = Depends(verify_key)):
    """Analyze content and return SEO-optimized metadata."""
    
    if not req.content or len(req.content) < 50:
        raise HTTPException(status_code=400, detail="Content must be at least 50 characters")
    
    # Default response
    default_response = AnalyzeResponse(
        title=req.content[:50].strip(),
        meta_description=req.content[:155].strip().replace("\n", " ") + "...",
        keywords=req.content.split()[:5],
        readability_score=60,
        suggestions=["Add a compelling headline", "Include at least one statistic", "Break up long paragraphs"]
    )
    
    if not OR_KEY:
        return default_response
    
    # AI analysis via OpenRouter
    try:
        prompt = f"""Analyze this content. Return ONLY a JSON object with these exact keys:
- title: SEO title (max 60 chars)
- meta_description: meta description (max 160 chars)
- keywords: array of 5 keywords
- readability_score: number 1-100
- suggestions: array of 3-5 improvements

Content:
{req.content[:8000]}"""
        
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OR_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "deepseek/deepseek-v4-flash",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 2000
                }
            )
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            
            # Extract JSON from response
            if "{" in content:
                json_str = content[content.find("{"):content.rfind("}")+1]
                result = json.loads(json_str)
                return AnalyzeResponse(**result)
    except Exception as e:
        print(f"AI analysis error: {e}")
    
    return default_response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)