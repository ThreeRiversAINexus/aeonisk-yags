-- Pandoc Lua filter to convert YAGS DocBook tables to Markdown
-- Version 3.0 with deep debugging and specialized handling for YAGS format

function dump(o)
   if type(o) == 'table' then
      local s = '{ '
      for k,v in pairs(o) do
         if type(k) ~= 'number' then k = '"'..k..'"' end
         s = s .. '['..k..'] = ' .. dump(v) .. ','
      end
      return s .. '} '
   else
      return tostring(o)
   end
end

-- Helper for detailed debug output
local function debug(msg)
  io.stderr:write("YAGS_DEBUG: " .. msg .. "\n")
end

-- Check for target and value attributes at any level
local function extract_deep_attributes(el, attr_name)
  -- If it's a direct attribute
  if el[attr_name] then
    return el[attr_name]
  end
  
  -- Try to get it from attr table
  if el.attr and el.attr[attr_name] then
    return el.attr[attr_name]
  end
  
  -- Try to get it from attributes table
  if el.attributes and el.attributes[attr_name] then
    return el.attributes[attr_name]
  end
  
  -- If el.attr has attributes
  if el.attr and el.attr.attributes and el.attr.attributes[attr_name] then
    return el.attr.attributes[attr_name]
  end
  
  -- Check for content recursively
  if el.content then
    for _, child in ipairs(el.content) do
      local result = extract_deep_attributes(child, attr_name)
      if result then
        return result
      end
    end
  end
  
  return nil
end

-- Helper to create a cell
local function create_cell(content)
  if type(content) == "string" then
    return {pandoc.Para(pandoc.Str(content))}
  elseif type(content) == "table" and content.t then
    return {content}
  elseif type(content) == "table" then
    return content
  else
    return {pandoc.Para(pandoc.Str(""))}
  end
end

-- Create a proper markdown table
local function create_table(caption, headers, rows)
  -- Ensure we have valid headers and rows
  if not headers or #headers == 0 then
    headers = {{pandoc.Para(pandoc.Str(""))}}
  end
  
  if not rows or #rows == 0 then
    rows = {{{pandoc.Para(pandoc.Str(""))}}}
  end
  
  -- Set up alignments
  local alignments = {}
  for i=1,#headers do
    alignments[i] = pandoc.AlignDefault
  end
  
  -- Set up widths
  local widths = {}
  for i=1,#headers do
    widths[i] = 1.0 / #headers
  end
  
  debug("Creating table with " .. #headers .. " columns and " .. #rows .. " rows")
  
  -- Create the table
  return pandoc.Table(
    caption or pandoc.Caption(),
    alignments,
    widths,
    headers,
    rows
  )
end

function Div(el)
  debug("Found Div with " .. #el.content .. " content items")
  
  -- Check if this is a targetlist div (often targetlist are wrapped in divs)
  local is_targetlist = false
  local attrs = {}
  
  if el.attr then
    debug("Div attributes: " .. dump(el.attr))
    if el.attr.classes and #el.attr.classes > 0 then
      for _, class in ipairs(el.attr.classes) do
        if class == "targetlist" then
          is_targetlist = true
          break
        end
      end
    end
  end
  
  if is_targetlist then
    debug("Found targetlist in Div!")
    
    -- Extract headers and rows
    local headers = {}
    local rows = {}
    
    -- Process headers from attributes
    local target_label = extract_deep_attributes(el, "targetLabel") or "Score"
    local value_label = extract_deep_attributes(el, "valueLabel") or "Value"
    local desc_label = "Description"
    
    table.insert(headers, create_cell(target_label))
    table.insert(headers, create_cell(value_label))
    table.insert(headers, create_cell(desc_label))
    
    -- Process rows from content
    if el.content then
      for i, item in ipairs(el.content) do
        if item.t == "BulletList" or item.t == "OrderedList" or item.t == "DefinitionList" then
          local row = {}
          
          -- Try to extract target/value
          local target_val = extract_deep_attributes(item, "target") or ""
          local value_val = extract_deep_attributes(item, "value") or ""
          local desc_val = {}
          
          if item.content and #item.content > 0 then
            desc_val = item.content
          end
          
          table.insert(row, create_cell(target_val))
          table.insert(row, create_cell(value_val))
          table.insert(row, desc_val or create_cell(""))
          
          table.insert(rows, row)
        end
      end
    end
    
    if #rows > 0 then
      return create_table(nil, headers, rows)
    end
  end
  
  return el
end

-- Helper to extract text representation of an inline element
local function stringify_inline(inline)
  if inline.t == "Str" then
    return inline.text
  elseif inline.t == "Space" then
    return " "
  elseif inline.t == "SoftBreak" or inline.t == "LineBreak" then
    return "\n"
  else
    return pandoc.utils.stringify(inline) or ""
  end
end

function DefinitionList(dl)
  debug("Processing DefinitionList with " .. #dl.content .. " items")
  
  -- Get attributes
  local targetFirst = extract_deep_attributes(dl, "targetFirst")
  local targetLabel = extract_deep_attributes(dl, "targetLabel")
  local valueLabel = extract_deep_attributes(dl, "valueLabel")
  
  -- Detect if this is a YAGS table by its attributes
  local is_yags_table = targetFirst or targetLabel or valueLabel
  
  if is_yags_table then
    debug("Found YAGS table (targetlist) in DefinitionList")
    
    -- Set up headers
    local headers = {}
    local col1_label = targetLabel or "Score"
    local col2_label = valueLabel or "Value"
    local col3_label = "Description"
    
    -- Default order
    if targetFirst == "true" or targetFirst == true then
      headers = {
        create_cell(col1_label),
        create_cell(col2_label),
        create_cell(col3_label)
      }
    else
      headers = {
        create_cell(col2_label),
        create_cell(col1_label),
        create_cell(col3_label)
      }
    end
    
    -- Process rows
    local rows = {}
    for i, item in ipairs(dl.content) do
      debug("Processing item " .. i)
      
      local term = item[1]  -- List of Inlines (term)
      local defs = item[2]  -- List of (list of Blocks) (definitions)
      
      -- Get target/value attributes from term
      local target_val = ""
      local value_val = ""
      
      -- Try to extract from term
      for _, inline in ipairs(term) do
        if not target_val and extract_deep_attributes(inline, "target") then
          target_val = extract_deep_attributes(inline, "target")
        end
        
        if not value_val and extract_deep_attributes(inline, "value") then
          value_val = extract_deep_attributes(inline, "value")
        end
      end
      
      -- If value is still empty, use the term text
      if value_val == "" then
        value_val = pandoc.utils.stringify(term)
      end
      
      -- Create the row cells
      local row = {}
      if targetFirst == "true" or targetFirst == true then
        table.insert(row, create_cell(target_val))
        table.insert(row, create_cell(value_val))
      else
        table.insert(row, create_cell(value_val))
        table.insert(row, create_cell(target_val))
      end
      
      -- Add definition content
      if defs and #defs > 0 then
        table.insert(row, defs[1] or create_cell(""))
      else
        table.insert(row, create_cell(""))
      end
      
      table.insert(rows, row)
    end
    
    if #rows > 0 then
      return create_table(nil, headers, rows)
    end
  end
  
  return dl
end

function BulletList(bl)
  debug("Processing BulletList with " .. #bl.content .. " items")
  
  -- Check if this is a YAGS itemlist with order="strict"
  local order = extract_deep_attributes(bl, "order")
  
  if order == "strict" then
    debug("Found YAGS strict itemlist in BulletList")
    
    -- Set up headers
    local headers = {
      create_cell("Level"),
      create_cell("Description")
    }
    
    -- Process rows
    local rows = {}
    for i, item in ipairs(bl.content) do
      local row = {}
      
      -- Try to get the name attribute
      local name_val = extract_deep_attributes(item, "name") or ""
      
      table.insert(row, create_cell(name_val))
      table.insert(row, item)
      
      table.insert(rows, row)
    end
    
    if #rows > 0 then
      return create_table(nil, headers, rows)
    end
  end
  
  return bl
end

function OrderedList(ol)
  debug("Processing OrderedList with " .. #ol.content .. " items")
  
  -- Check for YAGS table attributes
  local order = extract_deep_attributes(ol, "order")
  
  if order == "1" then
    debug("Found YAGS numbered itemlist in OrderedList")
    
    -- Set up headers
    local headers = {
      create_cell("Number"),
      create_cell("Description")
    }
    
    -- Process rows
    local rows = {}
    for i, item in ipairs(ol.content) do
      local row = {}
      
      table.insert(row, create_cell(tostring(i)))
      table.insert(row, item)
      
      table.insert(rows, row)
    end
    
    if #rows > 0 then
      return create_table(nil, headers, rows)
    end
  end
  
  return ol
end

-- For direct table conversion from DocBook table to Pandoc table
function Table(tbl)
  debug("Found a Table element")
  -- Already a table, just return it
  return tbl
end

-- Check Block elements that might contain tables
function Block(block)
  debug("Checking Block of type " .. block.t)
  
  -- Check if this block has any table-like attributes
  local targetFirst = extract_deep_attributes(block, "targetFirst")
  local targetLabel = extract_deep_attributes(block, "targetLabel")
  local valueLabel = extract_deep_attributes(block, "valueLabel")
  local order = extract_deep_attributes(block, "order")
  
  if targetFirst or targetLabel or valueLabel or order then
    debug("Found potential YAGS table in Block of type " .. block.t)
    -- Specific handling could be added here
  end
  
  return block
end

-- Return all filter functions
return {
  Div = Div,
  DefinitionList = DefinitionList,
  BulletList = BulletList,
  OrderedList = OrderedList,
  Table = Table,
  Block = Block
}
