# Context Gathering Procedures

These procedures replace the TypeScript `context-extractor.ts` module. They describe how to gather and compress context when acting as each agent. Follow these procedures to manage context efficiently.

## Character Registry (Tier 1 Summary) — `buildCharacterRegistry`

When you need a lightweight overview of all characters:

1. Use Glob to find: `characters/protagonist.md`, `characters/antagonist.md`, `characters/supporting/*.md`
2. For each file, read only the YAML front-matter (the content between the `---` markers at the top)
3. Build a summary table with columns: Name | Identity | Role | Key Traits | Language Style
4. Also build a quick relationship list from the `relationships` field in front-matter
5. Target: ~500-1000 characters total regardless of character count

This is the "Tier 1" context — always load this when any agent needs character information.

## Character Quick Card — `buildCharacterQuickCard`

When you need detailed info for a specific character:

1. Read the character's full file
2. Extract from YAML front-matter: name, role, identity, age, traits, relationships, growth_arc, language_style
3. From the body, extract: key background events, motivation, ability summary
4. Present as a compressed card (~300-500 chars)

## Chapter Narrative Weave Extraction — `extractChapterNarrativeWeave`

When writing or reviewing a specific chapter, extract only chapter-relevant content from `narrative-weave.md`:

1. Read `narrative-weave.md`
2. Find the foreshadowing table (section with `| 编号 | 类型 | ...`) — filter rows where the chapter column matches current chapter
3. Find the foreshadowing planting checklist — filter for current chapter entries
4. Find the recovery/resolution status — filter for current chapter entries
5. Find any "unprocessed signals" for this chapter
6. Include the subplot table rows relevant to this chapter
7. Skip all other chapters' entries

## Chapter Art Design Extraction — `extractChapterArtDesign`

When writing or reviewing a specific chapter, extract from `art-design.md`:

1. Read `art-design.md`
2. Find the per-chapter emotional beat table — filter for current chapter row
3. Find the imagery definitions that are relevant to this chapter
4. Find the per-chapter narrative technique application table — filter for current chapter
5. Skip other chapters' entries

## Chapter-to-Act Mapping

To determine which act a chapter belongs to, follow this priority:

1. **Blueprint priority**: Read `blueprint.md` and look for act definitions with chapter ranges (e.g., `name: "第一幕"\nchapters: [4, 15]`). Parse each act's chapter range and match the target chapter number.
2. **Default fallback** (if blueprint has no parseable act ranges):
   - Act 0 (序篇): ch1-3
   - Act 1 (第一幕): ch4-15
   - Act 2 (第二幕): ch16-30
   - Act 3 (第三幕): ch31-45
   - Act 4 (终篇): ch46-50

   Note: This default assumes a 50-chapter novel. For novels with different chapter counts, the blueprint MUST define act ranges explicitly.

## Style Stage Notes Extraction — `extractStyleStageNotes`

Extract stage-specific style rules from `style-guide.md` based on which act the chapter belongs to (use the Chapter-to-Act Mapping procedure above to determine the act).

Extract these sections:
1. Overall tone and writing style rules
2. Sentence norms and key prohibitions
3. Dual-timeline style notes (if applicable)
4. Style evolution trajectory row for the current act
5. Chapter structure norms

## World Quick Reference — `buildWorldQuickRef`

Compress world setting for agents that need world context but not full detail:

1. Read `world/setting.md` — keep: all headers, all tables, all bullet points, short lines (< 150 chars). Skip: long descriptive paragraphs (max 5 per section)
2. Read `world/rules.md` — extract: power system summary (source, levels, key limitations), combat/magic system basics
3. Combine into a concise reference (~1000-2000 chars)

## Narrative Weave Summary — `buildNarrativeWeaveSummary`

For agents that need the full-book narrative weave overview:

1. Read `narrative-weave.md` in full
2. Keep structural tables intact (foreshadowing table, subplot table, easter egg table) — these are per-item definitions
3. Compress prose sections (relationship maps, subplot timelines, technique plans) to headers + first few lines
4. Target: ~50% of original size

## Art Design Summary — `buildArtDesignSummary`

For agents that need the full-book art design overview:

1. Read `art-design.md` in full
2. Keep imagery definitions and prose overviews in full
3. Compress per-chapter tables (emotional beats, narrative technique application) to per-act summaries (use Chapter-to-Act Mapping procedure to determine act boundaries)
4. For emotional beats: aggregate by act (average intensity, dominant emotions)
5. For techniques: list techniques used per act
6. Target: ~50% of original size

## Previous Chapter Summary — `buildPreviousChapterSummary`

When writing a new chapter, extract writing notes from the previous chapter:

1. Read the previous chapter file
2. Look for a `### 写作备注` section (H3 heading)
3. Extract that section in full — it contains: word count, foreshadowing operations, subplot progress, character state updates, next-chapter hooks
4. If no notes section found, extract the last 300 characters as fallback
5. Also include the full previous chapter text for continuity

## Context Assembly for Chapter Writing

When acting as the chapter-writer, assemble context in this order:

1. Chapter outline (full content from `outline/chapters/chXX.md`)
2. Style guide stage notes (extract using Style Stage Notes procedure)
3. World quick reference (compress using World Quick Ref procedure)
4. Character registry (build using Character Registry procedure)
5. Narrative weave excerpt (extract using Chapter Narrative Weave procedure)
6. Art design excerpt (extract using Chapter Art Design procedure)
7. Previous chapter summary (extract using Previous Chapter Summary procedure)
8. Previous chapter full text

## Context Assembly for Editor Review

When acting as the editor, assemble:

1. Chapter text (full)
2. Art design summary (compress using Art Design Summary procedure)
3. Narrative weave summary (compress using Narrative Weave Summary procedure)
4. World quick reference (compress using World Quick Ref procedure)
5. Character registry (build using Character Registry procedure)

## Context Assembly for Consistency Check

When acting as the consistency-checker:

1. All chapter files — latest chapter gets full text, all prior chapters get only writing notes summaries
2. Art design summary
3. Narrative weave summary
4. World quick reference
5. `world/timeline.md` (full)
6. Character registry
