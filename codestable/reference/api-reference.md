# AI Novel Dehydrator -- API Reference

> Auto-generated from source code. Last scanned: 2026-04-25.

---

## Table of Contents

- [API Endpoints](#api-endpoints)
  - [Books](#books)
  - [Index](#index)
  - [Dehydrate](#dehydrate)
  - [QA](#qa)
- [Pydantic Models](#pydantic-models)
- [Public Service Functions](#public-service-functions)

---

## API Endpoints

Base URL: `http://localhost:8000`

All endpoints are registered under the `/api` prefix via four FastAPI routers:
- `/api/books` -- book upload and status
- `/api/index` -- novel indexing
- `/api/dehydrate` -- chapter dehydration
- `/api/qa` -- Q&A over indexed novels

---

### Books

#### POST /api/books/upload

Upload a novel text file (`.txt`) to the system. The file content is decoded as UTF-8, a `book_id` is generated, and the original text is persisted.

**Request**

| Field | Type | Location | Required |
|---|---|---|---|
| `file` | `multipart/form-data` file | Body | Yes |

The file content must be valid UTF-8 text.

**Response**

| Field | Type | Description |
|---|---|---|
| `book_id` | `str` | Unique identifier for the uploaded book |

**Status Codes**

| Code | Condition |
|---|---|
| 200 | Upload successful |
| 422 | Invalid request body |

**Example**

```bash
curl -X POST http://localhost:8000/api/books/upload \
  -F "file=@my-novel.txt"
```

```json
{ "book_id": "a1b2c3d4e5f6" }
```

---

#### GET /api/books/{book_id}/status

Retrieve the current processing status of a book, including whether it has been indexed and/or dehydrated.

**Path Parameters**

| Field | Type | Description |
|---|---|---|
| `book_id` | `str` | The book identifier |

**Response**

Returns a JSON object with status fields (exact shape depends on `Storage.get_status` implementation).

**Example**

```bash
curl http://localhost:8000/api/books/a1b2c3d4e5f6/status
```

---

### Index

#### POST /api/index/{book_id}

Trigger full-text indexing for a book. Parses chapters, extracts characters/plot/foreshadows/items via LLM in batches, merges results into a `GlobalContext`, and persists it.

**Path Parameters**

| Field | Type | Description |
|---|---|---|
| `book_id` | `str` | The book identifier |

**Request Body**

None required.

**Response**

| Field | Type | Description |
|---|---|---|
| `book_id` | `str` | The book identifier |
| `context` | `GlobalContext \| null` | The extracted global context (present on success) |
| `status` | `str` | `"completed"` or `"failed"` |
| `error` | `str \| null` | Error message if status is `"failed"` |

**Status Codes**

| Code | Condition |
|---|---|
| 200 | Indexing completed (success or failure captured in response) |
| 404 | Book not found |

**Example**

```bash
curl -X POST http://localhost:8000/api/index/a1b2c3d4e5f6
```

```json
{
  "book_id": "a1b2c3d4e5f6",
  "context": {
    "book_title": "my-novel.txt",
    "total_chapters": 120,
    "characters": [...],
    "main_plot": [...],
    "foreshadows": [...],
    "key_items": [...]
  },
  "status": "completed",
  "error": null
}
```

---

#### GET /api/index/{book_id}/context

Retrieve the persisted `GlobalContext` for an indexed book.

**Path Parameters**

| Field | Type | Description |
|---|---|---|
| `book_id` | `str` | The book identifier |

**Response**

Returns the `GlobalContext` object directly.

**Status Codes**

| Code | Condition |
|---|---|
| 200 | Context found |
| 404 | Context not found (book not indexed) |

**Example**

```bash
curl http://localhost:8000/api/index/a1b2c3d4e5f6/context
```

---

### Dehydrate

#### POST /api/dehydrate/{book_id}

Run the dehydration pipeline on a book. Parses chapters, classifies each text block via LLM (keep/summarize/delete), assembles the output, and persists the dehydrated text.

This is a synchronous endpoint -- the request blocks until all chapters are processed.

**Path Parameters**

| Field | Type | Description |
|---|---|---|
| `book_id` | `str` | The book identifier |

**Request Body**

None required.

**Response**

| Field | Type | Description |
|---|---|---|
| `status` | `str` | `"completed"` |
| `total_chapters` | `int` | Number of chapters processed |

**Status Codes**

| Code | Condition |
|---|---|
| 200 | Dehydration completed |
| 404 | Book not found, or context not found |

**Example**

```bash
curl -X POST http://localhost:8000/api/dehydrate/a1b2c3d4e5f6
```

```json
{ "status": "completed", "total_chapters": 120 }
```

---

#### GET /api/dehydrate/{book_id}/progress

Retrieve the dehydration progress for a book.

> **MVP note:** This is a simplified implementation that returns only `completed` or `not_started`. Full SSE-based streaming progress is planned for a future iteration.

**Path Parameters**

| Field | Type | Description |
|---|---|---|
| `book_id` | `str` | The book identifier |

**Response**

| Field | Type | Description |
|---|---|---|
| `chapter` | `int` | Current chapter number (MVP: always 0) |
| `total` | `int` | Total chapter count (MVP: always 0) |
| `status` | `str` | `"completed"` or `"not_started"` |

**Example**

```bash
curl http://localhost:8000/api/dehydrate/a1b2c3d4e5f6/progress
```

```json
{ "chapter": 0, "total": 0, "status": "completed" }
```

---

#### GET /api/dehydrate/{book_id}/output

Retrieve the full dehydrated text output for a book.

**Path Parameters**

| Field | Type | Description |
|---|---|---|
| `book_id` | `str` | The book identifier |

**Response**

| Field | Type | Description |
|---|---|---|
| `text` | `str` | The complete dehydrated text |

**Status Codes**

| Code | Condition |
|---|---|
| 200 | Output found |
| 404 | Dehydrated output not found (book not yet dehydrated) |

**Example**

```bash
curl http://localhost:8000/api/dehydrate/a1b2c3d4e5f6/output
```

```json
{ "text": "...dehydrated novel text..." }
```

---

### QA

#### POST /api/qa/ask

Ask a natural-language question about an indexed book. The system searches relevant chapters via keyword matching against character names and key items, then generates an answer using the LLM with both the retrieved text and the global context.

**Request Body**

| Field | Type | Required | Description |
|---|---|---|---|
| `book_id` | `str` | Yes | The book identifier |
| `question` | `str` | Yes | The question to ask |

**Response**

| Field | Type | Description |
|---|---|---|
| `answer` | `str` | The generated answer |
| `source_chapters` | `list[int]` | Chapter numbers referenced in the answer |

**Status Codes**

| Code | Condition |
|---|---|
| 200 | Answer generated |
| 404 | Book not found, or context not found |

**Example**

```bash
curl -X POST http://localhost:8000/api/qa/ask \
  -H "Content-Type: application/json" \
  -d '{"book_id": "a1b2c3d4e5f6", "question": "主角是谁？"}'
```

```json
{
  "answer": "主角是张三，他在第一章登场...",
  "source_chapters": [1, 3, 7]
}
```

---

## Pydantic Models

### Layer

> Source: `app/models/dehydration.py`

Enum classifying how a text block should be handled during dehydration.

| Value | Description |
|---|---|
| `keep` | Keep the block verbatim in the output |
| `summarize` | Replace the block with an LLM-generated summary |
| `delete` | Drop the block from the output entirely |

---

### BlockResult

> Source: `app/models/dehydration.py`

Result of classifying and processing a single text block.

| Field | Type | Description |
|---|---|---|
| `text` | `str` | Original block text |
| `layer` | `Layer` | Classification: `keep`, `summarize`, or `delete` |
| `output` | `str` | Processed output (original text, summary, or empty) |

---

### CharacterProfile

> Source: `app/models/context.py`

Metadata about a character extracted during indexing.

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | -- | Character name |
| `role` | `str` | -- | Role type (e.g., `主角`, `配角`, `反派`, `其他`) |
| `relationships` | `list[str]` | `[]` | List of relationship descriptions |
| `first_chapter` | `int` | -- | Chapter number of first appearance |
| `last_chapter` | `int` | -- | Chapter number of last appearance |

---

### Foreshadow

> Source: `app/models/context.py`

A foreshadowing element tracked across the novel.

| Field | Type | Default | Description |
|---|---|---|---|
| `description` | `str` | -- | Description of the foreshadowing element |
| `setup_chapter` | `int` | -- | Chapter where the foreshadow was introduced |
| `resolved` | `bool` | `False` | Whether the foreshadow has been resolved |

---

### GlobalContext

> Source: `app/models/context.py`

Complete indexed context for a novel, aggregating all batch extractions.

| Field | Type | Description |
|---|---|---|
| `book_title` | `str` | Book title |
| `total_chapters` | `int` | Total chapter count |
| `characters` | `list[CharacterProfile]` | All extracted characters |
| `main_plot` | `list[str]` | Main plot line items |
| `foreshadows` | `list[Foreshadow]` | Tracked foreshadowing elements |
| `key_items` | `list[str]` | Important objects/items in the story |

---

### PartialContext

> Source: `app/models/context.py`

Extraction result from a single LLM batch (before merging).

| Field | Type | Description |
|---|---|---|
| `characters` | `list[dict]` | Character dicts from this batch |
| `plot` | `list[str]` | Plot items from this batch |
| `foreshadows` | `list[dict]` | Foreshadow dicts from this batch |
| `key_items` | `list[str]` | Key items from this batch |

---

### IndexResponse

> Source: `app/models/context.py`

Response model for the `POST /api/index/{book_id}` endpoint.

| Field | Type | Default | Description |
|---|---|---|---|
| `book_id` | `str` | -- | Book identifier |
| `context` | `GlobalContext \| None` | `None` | Extracted context (present on success) |
| `status` | `str` | -- | `"completed"` or `"failed"` |
| `error` | `str \| None` | `None` | Error message on failure |

---

### DehydrateRequest

> Source: `app/models/dehydration.py`

> **Note:** This model is defined but not used as a request body in any current route. The dehydrate endpoint derives chapter data from stored context and original text. It is available for programmatic use.

| Field | Type | Description |
|---|---|---|
| `book_id` | `str` | Book identifier |
| `chapter_number` | `int` | Chapter number to dehydrate |
| `chapter_text` | `str` | Raw chapter text |

---

### DehydrateResponse

> Source: `app/models/dehydration.py`

> **Note:** This model is defined but not used as a response in any current route. It represents the shape of a single-chapter dehydration result.

| Field | Type | Description |
|---|---|---|
| `book_id` | `str` | Book identifier |
| `chapter_number` | `int` | Chapter number |
| `blocks` | `list[BlockResult]` | Classified block results |
| `dehydrated_text` | `str` | Assembled dehydrated text for this chapter |

---

### AskRequest

> Source: `app/models/qa.py`

Request body for `POST /api/qa/ask`.

| Field | Type | Description |
|---|---|---|
| `book_id` | `str` | Book identifier |
| `question` | `str` | The question to ask |

---

### AskResponse

> Source: `app/models/qa.py`

Response body for `POST /api/qa/ask`.

| Field | Type | Description |
|---|---|---|
| `answer` | `str` | The generated answer |
| `source_chapters` | `list[int]` | Referenced chapter numbers |

---

## Public Service Functions

These functions are the programmatic entry points into the core pipeline logic, independent of the HTTP layer.

---

### `index_novel`

> Source: `app/modules/indexer/service.py`

Full-text indexing entry point. Parses chapters, extracts context via LLM in configurable batches, then merges partial results into a unified `GlobalContext`.

**Signature**

```python
async def index_novel(
    book_id: str,
    original_text: str,
    book_title: str,
) -> GlobalContext
```

**Parameters**

| Name | Type | Description |
|---|---|---|
| `book_id` | `str` | Unique book identifier |
| `original_text` | `str` | The full novel text |
| `book_title` | `str` | Title for the global context |

**Return Type**

`GlobalContext` -- the merged, deduplicated indexing result.

**Example**

```python
from app.modules.indexer.service import index_novel

text = open("novel.txt").read()
ctx = await index_novel(
    book_id="my-book",
    original_text=text,
    book_title="My Novel",
)
print(f"Found {ctx.total_chapters} chapters, {len(ctx.characters)} characters")
```

---

### `dehydrate_chapter`

> Source: `app/modules/dehydration/service.py`

Classify and process a single chapter's text. Splits into blocks (<=800 chars, paragraph-aligned), sends each block to the LLM for classification (keep/summarize/delete), and returns the structured results.

**Signature**

```python
async def dehydrate_chapter(
    chapter_text: str,
    context: GlobalContext,
) -> list[BlockResult]
```

**Parameters**

| Name | Type | Description |
|---|---|---|
| `chapter_text` | `str` | The raw chapter text |
| `context` | `GlobalContext` | The indexed global context for the book |

**Return Type**

`list[BlockResult]` -- one result per text block, each with layer classification and processed output.

**Example**

```python
from app.modules.dehydration.service import dehydrate_chapter, assemble_dehydrated

chapter = "The protagonist walked into the dark forest..."
blocks = await dehydrate_chapter(chapter, ctx)
dehydrated = assemble_dehydrated(blocks)
print(dehydrated)
```

---

### `assemble_dehydrated`

> Source: `app/modules/dehydration/service.py`

Assemble a list of `BlockResult` into a single dehydrated string. Blocks classified as `DELETE` are skipped; all others are joined with double newlines.

**Signature**

```python
def assemble_dehydrated(
    blocks: list[BlockResult],
) -> str
```

**Parameters**

| Name | Type | Description |
|---|---|---|
| `blocks` | `list[BlockResult]` | Classified block results |

**Return Type**

`str` -- the assembled dehydrated text.

**Example**

```python
from app.modules.dehydration.service import assemble_dehydrated

text = assemble_dehydrated(blocks)
# DELETE blocks are omitted, others joined with "\n\n"
```

---

### `ask_question`

> Source: `app/modules/qa_assistant/service.py`

Answer a natural-language question about the novel. Searches for relevant chapters via keyword matching (character names, key items), then generates an answer using the LLM with both retrieved text and global context.

**Signature**

```python
async def ask_question(
    question: str,
    original_text: str,
    context: GlobalContext,
) -> AskResponse
```

**Parameters**

| Name | Type | Description |
|---|---|---|
| `question` | `str` | The user's question |
| `original_text` | `str` | The full novel text (for chapter search) |
| `context` | `GlobalContext` | The indexed global context |

**Return Type**

`AskResponse` -- contains the generated answer and list of referenced chapter numbers.

**Example**

```python
from app.modules.qa_assistant.service import ask_question

result = await ask_question(
    question="主角的性格有什么变化？",
    original_text=full_text,
    context=ctx,
)
print(result.answer)
print(f"Chapters: {result.source_chapters}")
```

---

### `parse_chapters`

> Source: `app/modules/indexer/chapter_parser.py`

Split novel text into chapters by detecting title lines matching the pattern `第X章` / `第X节` / `第X回` / `第X卷`. Falls back to fixed-size chunking (3000 chars) if no chapter titles are found.

**Signature**

```python
def parse_chapters(
    text: str,
) -> list[dict]
```

**Parameters**

| Name | Type | Description |
|---|---|---|
| `text` | `str` | The full novel text |

**Return Type**

`list[dict]` -- each dict has keys `number` (int), `title` (str), `text` (str). Auto-split chunks also include `auto_split: bool = True`.

**Example**

```python
from app.modules.indexer.chapter_parser import parse_chapters

chapters = parse_chapters(novel_text)
for ch in chapters:
    print(f"Chapter {ch['number']}: {ch['title']} ({len(ch['text'])} chars)")
```
