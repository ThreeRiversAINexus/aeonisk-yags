-- Print-safe glyph substitution for Aeonisk canon documents.
--
-- The status marks in NEXUS_LAW (✅ ratified, 🔨 proposed) and the ✅/❌ pairs
-- in FACTION_REFERENCE are load-bearing: a reader who loses them loses the
-- distinction the document is making. xelatex silently drops any codepoint the
-- font lacks, so an unfiltered PDF build discards them without erroring.
--
-- DejaVu covers every symbol in canon except these four, so map them onto
-- shapes it does have rather than deleting them or depending on an emoji font.

local substitutions = {
  ["\u{2705}"] = "\u{2713}",  -- ✅ heavy check   -> ✓ check
  ["\u{274C}"] = "\u{2717}",  -- ❌ cross mark    -> ✗ ballot X
  ["\u{1F528}"] = "\u{2692}", -- 🔨 hammer        -> ⚒ hammer and pick
  ["\u{2E3B}"] = "\u{2014}\u{2014}\u{2014}", -- ⸻ three-em dash -> ———
  ["\u{1F512}"] = "[locked]",  -- 🔒 padlock, no DejaVu glyph and no near shape
  ["\u{FE0F}"] = "",          -- emoji variation selector, no glyph of its own
}

function Str(elem)
  local text = elem.text
  for from, to in pairs(substitutions) do
    text = text:gsub(from, to)
  end
  if text ~= elem.text then
    return pandoc.Str(text)
  end
end

function Code(elem)
  local text = elem.text
  for from, to in pairs(substitutions) do
    text = text:gsub(from, to)
  end
  elem.text = text
  return elem
end

function CodeBlock(elem)
  local text = elem.text
  for from, to in pairs(substitutions) do
    text = text:gsub(from, to)
  end
  elem.text = text
  return elem
end
