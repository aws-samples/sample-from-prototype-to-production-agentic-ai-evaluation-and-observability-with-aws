# Structured Output with LLM-as-Judge

Sometimes your agent produces structured output (JSON, a filled form, a schema-conforming response) and you use an LLM-as-judge to verify correctness. This is still objective evaluation because there is a concrete, tangible expected output to compare against.

The difference from free-form LLM-as-judge (which is subjective) is that here the judge has a reference answer or schema to check against. It is verifying facts, field values, and structural correctness, not making a taste judgment. Examples: extracting structured data from documents, filling out forms from conversations, or generating API call parameters.
