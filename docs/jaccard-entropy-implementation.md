# Jaccard Similarity Entropy Implementation

## Overview
Replaced "debate entropy" with **Jaccard Similarity Entropy** calculation in the FastAPI `/generate` endpoint. This metric quantifies the semantic divergence between consecutive AI agent responses in discussions.

## What is Jaccard Similarity Entropy?

### Jaccard Similarity Index
- **Formula**: `|Intersection| / |Union|` of word sets
- **Range**: 0 to 1
  - `1.0` = identical word sets (maximum similarity)
  - `0.0` = no common words (minimum similarity)

### Entropy Score (Divergence Metric)
- **Formula**: `1 - Jaccard Similarity`
- **Range**: 0 to 1
  - `0.0` = identical texts (no divergence)
  - `1.0` = completely different texts (maximum divergence)

### Practical Interpretation
| Entropy Score | Meaning | Response Behavior |
|---|---|---|
| `0.0000` | Identical | Agents repeating exact content |
| `< 0.4` | High Similarity | Agents converging on common points |
| `≈ 0.5` | Moderate Similarity | Balanced discussion progression |
| `> 0.6` | Low Similarity | Agents exploring different angles |
| `1.0000` | Completely Different | Completely divergent discussion |

## Implementation Details

### 1. Helper Function: `_clean_text(text: str) -> Set[str]`
```python
def _clean_text(text: str) -> str:
    """Clean text for Jaccard Similarity: lowercase, remove punctuation, tokenize into words."""
    text = text.lower()
    text = re.sub(f"[{re.escape(string.punctuation)}]", " ", text)
    words = set(word for word in text.split() if word.strip())
    return words
```

**Processing Steps:**
1. Convert to lowercase for case-insensitive comparison
2. Remove all punctuation
3. Split by whitespace into tokens
4. Remove duplicates by converting to `set`
5. Filter out empty strings

**Performance**: O(n) where n = text length

### 2. Main Function: `calculate_jaccard_entropy(text1: str, text2: str) -> float`

**Logic:**
1. **Edge Cases:**
   - Both empty → entropy = 0.0 (identical)
   - One empty → entropy = 1.0 (completely different)
   - After cleaning, empty sets → entropy = 1.0 (different)

2. **Jaccard Calculation (optimized with set operations):**
   ```python
   intersection = len(words_text1 & words_text2)  # Set intersection O(min(n,m))
   union = len(words_text1 | words_text2)         # Set union O(n+m)
   jaccard_similarity = intersection / union if union > 0 else 0.0
   ```

3. **Entropy Conversion:**
   ```python
   entropy = 1.0 - jaccard_similarity
   return round(entropy, 4)  # 4 decimal precision
   ```

**Performance**: O(n + m) where n, m = text lengths

### 3. Pydantic Models

#### `GenerateRequest`
```python
class GenerateRequest(BaseModel):
    session_id: UUID                                  # Unique session
    topic: str                                        # Discussion topic
    agent_id: str                                     # Agent to generate response
    previous_response: Optional[str] = None           # Previous response for entropy
```

#### `TelemetryData`
```python
class TelemetryData(BaseModel):
    entropy: float                                    # Jaccard Entropy Score (0.0-1.0)
    latency_ms: int                                   # Response latency in milliseconds
    word_count: int                                   # Total words in response
```

#### `GenerateResponse`
```python
class GenerateResponse(BaseModel):
    response: str                                     # Generated response text
    telemetry: TelemetryData                         # Telemetry metrics object
    message_id: Optional[UUID] = None                # Message ID if persisted
    turn_number: Optional[int] = None                # Turn number if persisted
```

### 4. Endpoint: `/generate` (POST)

**Route**: `POST /generate`

**Request Body:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "topic": "The future of AI",
  "agent_id": "agent_alpha",
  "previous_response": "AI will revolutionize many industries..."
}
```

**Response (Success 200):**
```json
{
  "response": "Building on that point, AI's impact extends beyond...",
  "telemetry": {
    "entropy": 0.5234,
    "latency_ms": 1250,
    "word_count": 85
  },
  "message_id": "660e8400-e29b-41d4-a716-446655440000",
  "turn_number": 3
}
```

**Logic Flow:**
1. Start latency timer
2. Fetch agent configuration
3. Build context prompt from session history (last 5 messages)
4. Call Hugging Face API for response generation
5. Calculate latency (end - start)
6. If `previous_response` provided:
   - Calculate Jaccard entropy between new response and previous
   - Otherwise: Set entropy to 0.0 (first turn default)
7. Calculate word count by splitting response
8. Create telemetry object
9. Persist message to Redis and Vector store
10. Return complete response with telemetry

**Error Handling:**
- Agent not found → 404
- LLM API error → 502
- Storage error → 500
- Generic errors → 500

## Integration Points

### File: `backend/main.py`

**Added Imports:**
```python
import re
import string
import time
from typing import Optional
```

**Added Functions:**
- `_clean_text(text: str) -> Set[str]`
- `calculate_jaccard_entropy(text1: str, text2: str) -> float`

**Added Route:**
- `@app.post("/generate")` - Main endpoint with telemetry

**Added Models:**
- `GenerateRequest`
- `GenerateResponse`
- `TelemetryData`

**Updated Route:**
- `@app.get("/")` - Added `/generate` to endpoint list

## Performance Characteristics

### Set Operations (Optimized)
- **Set intersection** (`&`): O(min(n, m))
- **Set union** (`|`): O(n + m)
- **Text cleaning** (regex + split): O(n)

### Overall Algorithm
- **Time Complexity**: O(n + m) where n, m = text lengths
- **Space Complexity**: O(n + m) for word sets
- **Typical Latency**: < 5ms for responses up to 2000 words

### Performance Optimization
- Python's native `set` operations use hash tables (highly optimized)
- Regex operations are compiled and cached
- No external NLP libraries required (dependency-light)
- Early-exit for edge cases (empty strings)

## Usage Examples

### Example 1: First Turn (No Entropy Reference)
```python
# First agent's response - no comparison
request = GenerateRequest(
    session_id=UUID(...),
    topic="Climate change",
    agent_id="climate_expert",
    previous_response=None  # No previous response
)
# Response entropy will be 0.0
```

### Example 2: Subsequent Turns (With Entropy)
```python
# Second agent's response - compared to first
request = GenerateRequest(
    session_id=UUID(...),
    topic="Climate change",
    agent_id="economist",
    previous_response="Rising temperatures affect crop yields..."
)
# Response entropy calculated relative to climate_expert's response
```

### Example 3: Test Case Results
See `test_jaccard.py` for comprehensive test cases showing:
- Identical texts: entropy = 0.0000
- Partially similar: entropy = 0.6667
- Completely different: entropy = 1.0000
- Edge cases (empty strings, subsets, etc.)

## Telemetry Metrics Explained

### Entropy Metric
- **Primary indicator** of discussion divergence
- Values closer to 0 = agents converging
- Values closer to 1 = agents exploring different angles
- Useful for detecting:
  - Redundant responses (high similarity)
  - Creative divergence (low similarity)
  - Discussion balance (monitoring entropy trend)

### Latency Metric
- **Time taken** to generate response (LLM API + processing)
- Includes: token generation, network I/O, entropy calculation
- Useful for:
  - Performance monitoring
  - Detecting API slowdowns
  - Optimizing batch sizes

### Word Count Metric
- **Response length** in words
- Useful for:
  - Ensuring substantive responses
  - Monitoring response consistency
  - Flagging truncated outputs

## Testing

**Test File**: `test_jaccard.py`

**Run Tests:**
```bash
python test_jaccard.py
```

**Test Coverage:**
1. Identical texts
2. Partially similar texts
3. Different topics
4. Completely different texts
5. Both empty strings
6. One empty string
7. Subset relationships

**Output**: Visual analysis of similarity/entropy for each test case

## Database Storage

### Redis Keys
- `message:{message_id}` - Full message record with telemetry metadata (optional future extension)
- `session:{session_id}:messages` - Ordered message IDs for chronological retrieval

### Vector Index
- `message_id` → `message_text` + metadata
- Enables semantic search on discussion content

## Future Enhancements

1. **Extended Telemetry Storage**
   - Store entropy scores in message metadata for historical analysis
   - Track entropy trends over session lifetime

2. **Entropy-Based Insights**
   - Recommend new angles when entropy drops below threshold
   - Detect discussion stagnation (high similarity)
   - Suggest topic pivots when entropy too high

3. **Performance Optimizations**
   - Cache frequently used text embeddings
   - Batch entropy calculations for multi-agent turns

4. **Alternative Metrics**
   - Cosine similarity (if word embeddings added)
   - Semantic divergence (if NLP library integrated)
   - n-gram overlap (for stylistic diversity)

## Compatibility

- **Python Version**: 3.10+ (confirms compatible)
- **FastAPI**: 0.95+
- **Pydantic**: V2
- **Dependencies**: Standard library only (re, string, time)
  - No external packages required beyond existing stack

## Debugging

**Enable Detailed Logging:**
```python
logger.info(
    "Generating response: session=%s, agent=%s, topic=%s",
    request.session_id,
    request.agent_id,
    request.topic,
)
```

**Check Entropy Calculation:**
- Entropy = 0.0 → Same content (check for copied responses)
- Entropy = 1.0 → Completely different (check for off-topic responses)
- Entropy ≈ 0.5 → Balanced divergence (expected for good discussions)

**Verify Latency:**
- Track `telemetry.latency_ms` for anomalies
- Compare against baseline performance
- Identify LLM API bottlenecks
