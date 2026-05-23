# Audio Safety Analyzer - Integration Example

## Complete Integration Flow

This document demonstrates how all components integrate together in the Audio Safety Analyzer.

## 1. Request Flow

```
Client → FastAPI → Service → Modules → Database → Response
```

## 2. Code Example: Complete Analysis

### Step 1: Client Uploads Audio File

```python
import requests

# Upload audio file
with open("conversation.mp3", "rb") as f:
    response = requests.post(
        "http://localhost:8000/api/v1/analyze",
        files={"file": f}
    )

result = response.json()
print(f"Analysis ID: {result['id']}")
print(f"Risk Score: {result['risk']['score']}")
print(f"Severity: {result['severity']}")
```

### Step 2: FastAPI Endpoint Receives Request

```python
# api/audio_analysis_routes.py

@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_audio(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    service: AudioSafetyService = Depends(get_service)
):
    # 1. Validate file
    extension = os.path.splitext(file.filename)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, "Unsupported format")
    
    # 2. Save file
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # 3. Call service
    result = await service.analyze_audio_file(
        filepath=filepath,
        filename=file.filename,
        db_session=db
    )
    
    return result
```

### Step 3: Service Orchestrates Pipeline

```python
# services/audio_safety_service.py

async def analyze_audio_file(self, filepath, filename, db_session):
    # Step 1: Transcription
    transcript, timeline = await self._transcribe_audio(filepath)
    # Output: "Hello, how are you? ..."
    
    # Step 2: Grooming Detection
    detection_results = await self._detect_grooming_patterns(transcript)
    # Output: {
    #   "findings": [...],
    #   "grouped_findings": [...],
    #   "summary": {...}
    # }
    
    # Step 3: Evidence Extraction
    evidence = await self._extract_evidence(detection_results['grouped_findings'])
    # Output: [{"category": "secrecy", "evidence": "Don't tell anyone", ...}]
    
    # Step 4: Risk Scoring
    risk_result = await self._calculate_risk_score(detection_results['grouped_findings'])
    # Output: {"score": 67.5, "level": "High", ...}
    
    # Step 5: Severity Classification
    severity = await self._classify_severity(risk_result['score'])
    # Output: "High"
    
    # Step 6: Statistics
    stats = await self._generate_statistics(...)
    # Output: {"total_words": 150, "total_findings": 5, ...}
    
    # Step 7: Rule-based Summary
    rule_summary = await self._generate_rule_summary(...)
    # Output: "Analysis detected 5 concerning patterns..."
    
    # Step 8: LLM Summary
    llm_summary = await self._generate_llm_summary(...)
    # Output: "This conversation shows signs of manipulation..."
    
    # Step 9: Database Save
    record = await self._save_to_database(...)
    # Output: AudioAnalysis record with ID
    
    # Step 10: Vector Storage
    await self._store_in_vector_db(record.id, transcript)
    
    # Step 11: PDF Report
    pdf_path = await self._generate_pdf_report(...)
    # Output: "reports/report_1.pdf"
    
    # Step 12: Build Response
    return self._build_response(...)
```

### Step 4: Grooming Detection Pipeline

```python
# modules/grooming_detector.py

def analyze_transcript(self, transcript, speaker_aware=True):
    # Split into sentences
    sentences = self._split_transcript(transcript)
    # Output: [
    #   {"text": "Don't tell anyone", "speaker": "Adult"},
    #   {"text": "Okay", "speaker": "Child"}
    # ]
    
    all_findings = []
    
    for i, sentence_data in enumerate(sentences):
        sentence = sentence_data["text"]
        speaker = sentence_data.get("speaker")
        
        # Get context
        previous = sentences[i-1]["text"] if i > 0 else None
        next_sent = sentences[i+1]["text"] if i < len(sentences)-1 else None
        
        # Analyze sentence
        findings = self.analyze_sentence(
            sentence=sentence,
            previous_sentence=previous,
            next_sentence=next_sent,
            speaker=speaker
        )
        
        all_findings.extend(findings)
    
    # Group duplicates
    grouped_findings = self.grouping_engine.group_findings(all_findings)
    
    # Create summary
    summary = self._create_summary(grouped_findings)
    
    return {
        "findings": all_findings,
        "grouped_findings": grouped_findings,
        "summary": summary,
        "metadata": {...}
    }
```

### Step 5: Sentence Analysis

```python
# modules/grooming_detector.py

def analyze_sentence(self, sentence, previous_sentence, next_sentence, speaker):
    # 1. Pattern Detection
    pattern_matches = self._detect_patterns(sentence)
    # Output: {"secrecy": {"count": 1, "matched_patterns": [...]}}
    
    # 2. Context Analysis
    context_result = self.context_analyzer.analyze_context(
        sentence=sentence,
        previous_sentence=previous_sentence,
        next_sentence=next_sentence
    )
    # Output: {
    #   "safe_context": False,
    #   "risk_context": True,
    #   "matched_risk_terms": ["secret", "don't tell"]
    # }
    
    # 3. Filter Analysis (Negation & Jokes)
    filter_result = self.combined_filter.analyze(
        sentence=sentence,
        previous_sentences=[previous_sentence] if previous_sentence else None,
        next_sentences=[next_sentence] if next_sentence else None
    )
    # Output: {
    #   "is_negated": False,
    #   "is_joke": False,
    #   "confidence_penalty": 0.0
    # }
    
    results = []
    
    for category, match_info in pattern_matches.items():
        # 4. Confidence Calculation
        pattern_strength = PATTERN_CONFIDENCE.get(category, 0.5)
        matched_text = match_info["matched_patterns"][0]["text"]
        
        confidence_result = self.confidence_calculator.calculate(
            category=category,
            matched_text=matched_text,
            sentence=sentence,
            pattern_strength=pattern_strength
        )
        # Output: {
        #   "confidence": 0.92,
        #   "breakdown": {...},
        #   "factors": ["exact_phrase_match", "risk_context"]
        # }
        
        base_confidence = confidence_result["confidence"]
        
        # 5. Apply Penalties
        final_confidence = base_confidence
        
        # Filter penalty
        if filter_result:
            filter_penalty = filter_result.get("confidence_penalty", 0.0)
            final_confidence = max(0.0, base_confidence - filter_penalty)
        
        # Context penalty (safe context like teacher)
        if context_result.get("safe_context"):
            final_confidence = max(0.0, final_confidence - 0.4)
        
        # Speaker penalty (authority figures)
        if speaker and any(role in speaker.lower() for role in ["teacher", "parent"]):
            final_confidence = max(0.0, final_confidence - 0.5)
        
        # 6. Build Finding
        if final_confidence >= self.min_confidence_threshold:
            result = {
                "category": category,
                "confidence": final_confidence,
                "evidence": sentence,
                "matched_text": matched_text,
                "severity": CATEGORY_METADATA[category].severity,
                "speaker": speaker,
                "context": context_result,
                "filters": filter_result,
                "scoring": {...}
            }
            results.append(result)
    
    return results
```

### Step 6: Risk Scoring

```python
# modules/risk_scorer.py

def calculate_score(self, findings):
    # Group by category
    category_findings = self._group_by_category(findings)
    # Output: {
    #   "secrecy": [finding1, finding2],
    #   "manipulation": [finding3]
    # }
    
    total_score = 0.0
    category_scores = {}
    
    for category, category_list in category_findings.items():
        # Sort by confidence
        sorted_findings = sorted(
            category_list,
            key=lambda x: x.get("confidence", 0),
            reverse=True
        )
        
        weight = self.weights.get(category, 5)
        category_score = 0.0
        
        # Apply diminishing returns
        for i, finding in enumerate(sorted_findings):
            confidence = finding.get("confidence", 0.5)
            
            # Diminishing factor: 1.0, 0.5, 0.25, 0.125, ...
            if i < len(self.DIMINISHING_FACTORS):
                factor = self.DIMINISHING_FACTORS[i]
            else:
                factor = self.DIMINISHING_FACTORS[-1] / (2 ** (i - len(self.DIMINISHING_FACTORS) + 1))
            
            # Calculate effective score
            effective_score = weight * confidence * factor
            category_score += effective_score
        
        category_scores[category] = {
            "total_score": category_score,
            "occurrence_count": len(sorted_findings),
            ...
        }
        total_score += category_score
    
    # Cap at 100
    final_score = min(100.0, total_score)
    
    # Classify risk level
    risk_level = self.classify_risk(final_score)
    
    return {
        "score": final_score,
        "level": risk_level,
        "breakdown": category_scores,
        "category_counts": {...}
    }
```

### Step 7: Database Persistence

```python
# services/audio_safety_service.py

async def _save_to_database(self, db_session, filename, transcript, findings, ...):
    record = AudioAnalysis(
        filename=filename,
        transcript=transcript,
        findings=json.dumps(findings),
        evidence=json.dumps(evidence),
        stats=json.dumps(stats),
        summary=rule_summary,
        llm_summary=llm_summary,
        severity=severity,
        risk_score=risk_score,
        pdf_path=""
    )
    
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    
    return record
```

### Step 8: Response to Client

```json
{
  "id": 1,
  "filename": "conversation.mp3",
  "transcript": "Full transcript text...",
  "timeline": [
    {"start": 0.0, "end": 2.5, "text": "Don't tell anyone", "speaker": "Adult"}
  ],
  "detection": {
    "findings": [
      {
        "category": "secrecy",
        "confidence": 0.92,
        "evidence": "Don't tell anyone",
        "matched_text": "don't tell anyone",
        "severity": "critical",
        "speaker": "Adult",
        "context": {
          "safe": false,
          "risk": true,
          "risk_terms": ["don't tell", "secret"]
        },
        "filters": {
          "is_negated": false,
          "is_joke": false
        }
      }
    ],
    "grouped_findings": [...],
    "summary": {
      "total_findings": 5,
      "category_distribution": {"secrecy": 2, "manipulation": 3},
      "risk_level": "high"
    }
  },
  "evidence": [
    {"category": "secrecy", "evidence": "Don't tell anyone", "confidence": 0.92}
  ],
  "risk": {
    "score": 67.5,
    "level": "High",
    "breakdown": {
      "secrecy": {
        "weight": 15,
        "occurrence_count": 2,
        "total_score": 20.7,
        "occurrences": [
          {"occurrence": 1, "confidence": 0.92, "diminishing_factor": 1.0, "effective_score": 13.8},
          {"occurrence": 2, "confidence": 0.85, "diminishing_factor": 0.5, "effective_score": 6.9}
        ]
      }
    }
  },
  "severity": "High",
  "stats": {
    "total_words": 150,
    "total_findings": 5,
    "category_distribution": {...}
  },
  "summaries": {
    "rule_based": "Analysis detected 5 concerning patterns...",
    "llm_based": "This conversation shows signs of manipulation..."
  },
  "pdf_report": "reports/report_1.pdf",
  "analysis_metadata": {
    "analyzed_at": "2026-05-22T12:00:00",
    "min_confidence_threshold": 0.3,
    "total_findings": 5
  }
}
```

## 3. Example: Teacher Conversation (Low Confidence)

### Input
```
Teacher: What time does school finish today?
Student: 3 PM
Teacher: Don't forget your homework
```

### Processing

```python
# Sentence: "What time does school finish today?"
# Speaker: "Teacher"

# 1. Pattern Detection
pattern_matches = {"school": {...}, "routine": {...}}

# 2. Context Analysis
context = {
    "safe_context": True,  # "teacher", "school" detected
    "risk_context": False,
    "matched_safe_terms": ["teacher", "school"]
}

# 3. Confidence Calculation
base_confidence = 0.75  # Pattern strength

# 4. Apply Penalties
# - Safe context penalty: -0.4
# - Speaker penalty (teacher): -0.5
final_confidence = 0.75 - 0.4 - 0.5 = -0.15 → 0.0

# Result: Below threshold (0.3), not included in findings
```

## 4. Example: Manipulation Pattern (High Confidence)

### Input
```
Adult: Don't tell your parents about our chat
Adult: They won't understand
Adult: Only I understand you
```

### Processing

```python
# Sentence 1: "Don't tell your parents about our chat"

# 1. Pattern Detection
pattern_matches = {
    "secrecy": {"matched_patterns": [{"text": "don't tell"}]},
    "parent_monitoring": {"matched_patterns": [{"text": "parents"}]}
}

# 2. Context Analysis
context = {
    "safe_context": False,
    "risk_context": True,
    "matched_risk_terms": ["don't tell", "secret"]
}

# 3. Confidence Calculation
base_confidence = 0.95  # High pattern strength for secrecy

# 4. Apply Bonuses
# - Exact phrase match: +0.15
# - Risk context: +0.15
final_confidence = 0.95 + 0.15 + 0.15 = 1.0 (capped)

# Result: High confidence finding

# Sentence 2: "They won't understand"
# Category: manipulation
# Confidence: 0.90

# Sentence 3: "Only I understand you"
# Category: manipulation
# Confidence: 0.92

# Risk Scoring:
# - secrecy: 15 * 1.0 * 1.0 = 15.0
# - manipulation (1st): 10 * 0.92 * 1.0 = 9.2
# - manipulation (2nd): 10 * 0.90 * 0.5 = 4.5 (diminished)
# Total: 28.7 → "Low" risk level
```

## 5. Chatbot Integration

```python
# Client asks question
response = requests.post(
    "http://localhost:8000/api/v1/chat",
    json={
        "report_id": 1,
        "question": "What are the main concerns?"
    }
)

# Service retrieves from vector DB
# modules/chatbot.py
def answer_question(report_id, question):
    # 1. Retrieve relevant chunks from ChromaDB
    results = collection.query(
        query_texts=[question],
        n_results=3
    )
    
    # 2. Build context
    context = "\n".join(results['documents'][0])
    
    # 3. Generate answer with LLM
    answer = llm.generate(
        prompt=f"Context: {context}\n\nQuestion: {question}\n\nAnswer:"
    )
    
    return {"answer": answer, "sources": results['documents'][0]}
```

## 6. Error Handling Example

```python
# Scenario: Transcription fails

# Service Layer
try:
    transcript, timeline = await self._transcribe_audio(filepath)
except Exception as e:
    logger.error(f"Transcription failed: {str(e)}")
    raise Exception(f"Transcription failed: {str(e)}")

# API Layer
try:
    result = await service.analyze_audio_file(...)
except Exception as e:
    logger.error(f"Analysis failed: {str(e)}", exc_info=True)
    raise HTTPException(
        status_code=500,
        detail=f"Analysis failed: {str(e)}"
    )

# Client receives:
{
    "detail": "Analysis failed: Transcription failed: Audio file corrupted"
}
```

## 7. Logging Example

```
2026-05-22 12:00:00 - audio_safety_service - INFO - Starting analysis for file: conversation.mp3
2026-05-22 12:00:05 - audio_safety_service - INFO - Transcription completed: 450 characters
2026-05-22 12:00:06 - audio_safety_service - INFO - Detection completed: 5 findings
2026-05-22 12:00:06 - audio_safety_service - INFO - Evidence extracted: 5 items
2026-05-22 12:00:06 - audio_safety_service - INFO - Risk score calculated: 67.5/100 (High)
2026-05-22 12:00:06 - audio_safety_service - INFO - Severity classified: High
2026-05-22 12:00:07 - audio_safety_service - INFO - Rule-based summary generated
2026-05-22 12:00:10 - audio_safety_service - INFO - LLM summary generated
2026-05-22 12:00:10 - audio_safety_service - INFO - Analysis saved to database with ID: 1
2026-05-22 12:00:11 - audio_safety_service - INFO - PDF report generated: reports/report_1.pdf
2026-05-22 12:00:11 - audio_safety_service - INFO - Analysis completed successfully for: conversation.mp3
```

## 8. Testing the Integration

```bash
# Start the server
python app_v2.py

# Test health check
curl http://localhost:8000/api/v1/health

# Test analysis
curl -X POST "http://localhost:8000/api/v1/analyze" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@test_audio.mp3"

# Test chatbot
curl -X POST "http://localhost:8000/api/v1/chat" \
  -H "Content-Type: application/json" \
  -d '{"report_id": 1, "question": "What are the main concerns?"}'

# View API docs
open http://localhost:8000/docs
```

This integration example shows how all components work together seamlessly to provide comprehensive audio safety analysis!
