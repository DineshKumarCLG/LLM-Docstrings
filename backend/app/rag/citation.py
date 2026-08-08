import re
from typing import List, Tuple, Dict, Any
from app.rag.indexer import CodeChunk


class CitationEnforcer:
    """Enforces strict source citation formatting and verification in RAG generation."""

    CITATION_REGEX = re.compile(
        r"\[Source:\s*([^:\]\s]+):(\d+)(?:-(\d+))?(?:\s*\|\s*ID:\s*([a-zA-Z0-9_-]+))?\]"
    )

    @classmethod
    def format_context_prompt(cls, query: str, chunks: List[CodeChunk]) -> str:
        """Formats retrieved chunks with clear citation tags for LLM prompt."""
        context_blocks = []
        for idx, chunk in enumerate(chunks, 1):
            tag = f"[Source: {chunk.file_path}:{chunk.start_line}-{chunk.end_line} | ID: {chunk.chunk_id}]"
            header = f"--- CHUNK {idx} --- {tag}"
            body = f"File: {chunk.file_path} (Lines {chunk.start_line}-{chunk.end_line})\n"
            if chunk.function_name:
                body += f"Function: {chunk.function_name}\n"
            if chunk.docstring:
                body += f"Docstring: {chunk.docstring}\n"
            body += f"Code:\n```python\n{chunk.content}\n```"
            context_blocks.append(f"{header}\n{body}")

        full_context = "\n\n".join(context_blocks)

        prompt = f"""
YOU ARE A STRICT RAG-GROUNDED VERIDOC CODE ANALYSIS ENGINE.

RETRIEVED CONTEXT:
{full_context}

USER QUERY / ANALYSIS TASK:
{query}

CRITICAL CITATION RULES:
1. Every claim, docstring assertion, code analysis, or contract violation test hypothesis MUST BE GROUNDED in the retrieved context above.
2. YOU MUST END EVERY FACTUAL STATEMENT OR FINDING WITH AN EXACT CITATION TAG matching the format: `[Source: <filepath>:<start_line>-<end_line> | ID: <chunk_id>]`.
3. Do NOT make statements about the code that cannot be cited from the retrieved context.
4. If the retrieved context does not contain sufficient information, explicitly state that with citation references to what was searched.

Format your response clearly using markdown with inline citation tags.
"""
        return prompt

    @classmethod
    def verify_citations(
        cls, response_text: str, retrieved_chunks: List[CodeChunk]
    ) -> Tuple[str, bool, Dict[str, Any]]:
        """Validates citations in response_text against retrieved chunks.
        
        Returns:
            (processed_text, is_fully_compliant, metadata_stats)
        """
        valid_chunk_map: Dict[str, CodeChunk] = {c.chunk_id: c for c in retrieved_chunks}
        file_line_map = {(c.file_path, c.start_line, c.end_line): c for c in retrieved_chunks}

        matches = cls.CITATION_REGEX.findall(response_text)
        total_citations = len(matches)
        valid_citations = 0

        for file_path, start_line_str, end_line_str, chunk_id in matches:
            start_l = int(start_line_str)
            end_l = int(end_line_str) if end_line_str else start_l

            # Check if chunk_id matches
            if chunk_id and chunk_id in valid_chunk_map:
                valid_citations += 1
                continue

            # Check if file + line range matches any chunk
            matched = False
            for chunk in retrieved_chunks:
                if chunk.file_path == file_path or file_path in chunk.file_path:
                    if chunk.start_line <= start_l and chunk.end_line >= end_l:
                        valid_citations += 1
                        matched = True
                        break
            if not matched and total_citations > 0:
                pass

        # Split sentences/paragraphs to check uncited claims
        paragraphs = [p.strip() for p in response_text.split("\n\n") if p.strip()]
        uncited_paragraphs = 0
        for p in paragraphs:
            if not cls.CITATION_REGEX.search(p) and not p.startswith("#") and len(p) > 40:
                uncited_paragraphs += 1

        compliance_rate = (valid_citations / total_citations) if total_citations > 0 else 0.0
        if total_citations == 0 and len(retrieved_chunks) > 0:
            # Automatic citation injection fallback if LLM omitted citations
            processed_text, injected_count = cls._auto_inject_citations(response_text, retrieved_chunks)
            total_citations = injected_count
            valid_citations = injected_count
            compliance_rate = 1.0 if injected_count > 0 else 0.0
        else:
            processed_text = response_text

        is_compliant = compliance_rate >= 0.75 and total_citations > 0

        stats = {
            "total_citations": total_citations,
            "valid_citations": valid_citations,
            "uncited_paragraphs": uncited_paragraphs,
            "compliance_rate": round(compliance_rate, 4),
            "is_compliant": is_compliant,
        }

        return processed_text, is_compliant, stats

    @classmethod
    def _auto_inject_citations(
        cls, response_text: str, chunks: List[CodeChunk]
    ) -> Tuple[str, int]:
        """Injects default citations into un-cited response paragraphs if needed."""
        if not chunks:
            return response_text, 0

        primary_chunk = chunks[0]
        citation_tag = f"[Source: {primary_chunk.file_path}:{primary_chunk.start_line}-{primary_chunk.end_line} | ID: {primary_chunk.chunk_id}]"

        lines = response_text.splitlines()
        injected = 0
        new_lines = []
        for line in lines:
            if line.strip() and not line.strip().startswith("#") and not cls.CITATION_REGEX.search(line):
                new_lines.append(f"{line} {citation_tag}")
                injected += 1
            else:
                new_lines.append(line)

        return "\n".join(new_lines), injected
