-- Improved Pandoc Lua filter to convert YAGS DocBook tables to Markdown
-- Version 4.0 with enhanced targetlist extraction and table formatting

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

-- Helper to extract plain text from a complex element
local function extract_text(el)
  if type(el) == "string" then
    return el
  elseif type(el) == "table" then
    if el.text then
      return el.text
    elseif el.content then
      local result = ""
      for _, item in ipairs(el.content) do
        result = result .. extract_text(item)
      end
      return result
    elseif el.t == "Str" then
      return el.text
    elseif el.t == "Space" then
      return " "
    elseif el.t == "SoftBreak" or el.t == "LineBreak" then
      return "\n"
    end
  end
  
  -- Try pandoc's stringify if available
  if pandoc and pandoc.utils and pandoc.utils.stringify then
    local result = pandoc.utils.stringify(el)
    if result and result ~= "" then
      return result
    end
  end
  
  return ""
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

-- Helper to create a cell with proper content
local function create_cell(content)
  if type(content) == "string" then
    return {pandoc.Para(pandoc.Str(content))}
  elseif type(content) == "table" and content.t then
    -- If it's already a proper element
    return {content}
  elseif type(content) == "table" and #content > 0 then
    -- If it's an array of blocks
    return content
  else
    return {pandoc.Para(pandoc.Str(tostring(content) or ""))}
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
  
  -- Create the table with appropriate structure for pandoc 2.9+
  return pandoc.Table(
    caption or {}, -- Empty caption or provided one
    {id = "", class = "yags-table", attr = {}},
    alignments,
    widths,
    headers,
    rows
  )
end

-- SPECIAL HANDLER: Process targetlist elements directly
function process_targetlist(el)
  debug("Processing targetlist element")
  
  -- Extract headers and rows
  local headers = {}
  local rows = {}
  
  -- Get table attributes
  local targetFirst = extract_deep_attributes(el, "targetFirst") or "true"
  local targetLabel = extract_deep_attributes(el, "targetLabel") or "Score"
  local valueLabel = extract_deep_attributes(el, "valueLabel") or "Value"
  
  -- Determine column order
  if targetFirst == "true" or targetFirst == true then
    table.insert(headers, create_cell(targetLabel))
    table.insert(headers, create_cell(valueLabel))
  else
    table.insert(headers, create_cell(valueLabel))
    table.insert(headers, create_cell(targetLabel))
  end
  
  -- Process items
  if el.content then
    for _, item in ipairs(el.content) do
      if item.t == "BulletList" or item.t == "OrderedList" or item.t == "DefinitionList" then
        for _, subitem in ipairs(item.content) do
          local row = {}
          
          -- Extract target and value
          local target_val = extract_deep_attributes(subitem, "target") or ""
          local value_val = extract_deep_attributes(subitem, "value") or ""
          local desc_content = {}
          
          -- Extract description content
          if subitem.content then
            desc_content = subitem.content
          elseif subitem[2] and subitem[2][1] then
            desc_content = subitem[2][1]
          end
          
          -- Create row in the right order
          if targetFirst == "true" or targetFirst == true then
            table.insert(row, create_cell(target_val))
            table.insert(row, create_cell(value_val))
          else
            table.insert(row, create_cell(value_val))
            table.insert(row, create_cell(target_val))
          end
          
          -- Add description if we're including a third column
          if desc_content and #desc_content > 0 then
            table.insert(headers, create_cell("Description"))
            table.insert(row, desc_content)
          end
          
          table.insert(rows, row)
        end
      end
    end
  end
  
  if #rows > 0 then
    return create_table(nil, headers, rows)
  end
  
  return el
end

function Div(el)
  debug("Found Div with " .. #el.content .. " content items")
  
  -- Check if this is a targetlist div (often targetlist are wrapped in divs)
  local is_targetlist = false
  
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
  
  -- Process targetlist divs
  if is_targetlist then
    debug("Found targetlist in Div!")
    
    -- Extract headers
    local targetFirst = extract_deep_attributes(el, "targetFirst") or "true"
    local targetLabel = extract_deep_attributes(el, "targetLabel") or "Target"
    local valueLabel = extract_deep_attributes(el, "valueLabel") or "Value"
    
    -- Setup headers
    local headers = {}
    if targetFirst == "true" or targetFirst == true then
      table.insert(headers, create_cell(targetLabel))
      table.insert(headers, create_cell(valueLabel))
    else
      table.insert(headers, create_cell(valueLabel))
      table.insert(headers, create_cell(targetLabel))
    end
    
    -- Process rows
    local rows = {}
    local include_desc = false
    
    -- Look for items in the content
    for _, item in ipairs(el.content) do
      if item.t == "BulletList" or item.t == "OrderedList" or item.t == "DefinitionList" then
        for _, listitem in ipairs(item.content) do
          local row = {}
          
          -- Extract target/value from item attributes
          local target_val = extract_deep_attributes(listitem, "target") or ""
          local value_val = extract_deep_attributes(listitem, "value") or ""
          
          -- Extract description from content
          local desc_content = listitem
          if listitem[2] and listitem[2][1] then
            desc_content = listitem[2][1]
            include_desc = true
          end
          
          -- Build row
          if targetFirst == "true" or targetFirst == true then
            table.insert(row, create_cell(target_val))
            table.insert(row, create_cell(value_val))
          else
            table.insert(row, create_cell(value_val))
            table.insert(row, create_cell(target_val))
          end
          
          -- Add description column if needed
          if include_desc then
            if #headers < 3 then
              table.insert(headers, create_cell("Description"))
            end
            table.insert(row, desc_content)
          end
          
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

-- Convert DefinitionList to table (handles typical YAGS DocBook list format)
function DefinitionList(dl)
  debug("Processing DefinitionList with " .. #dl.content .. " items")
  
  -- Extract attributes
  local targetFirst = extract_deep_attributes(dl, "targetFirst")
  local targetLabel = extract_deep_attributes(dl, "targetLabel")
  local valueLabel = extract_deep_attributes(dl, "valueLabel")
  
  -- Check if this is a YAGS table format
  local is_yags_table = targetFirst or targetLabel or valueLabel
  
  if is_yags_table then
    debug("Found YAGS table in DefinitionList")
    
    -- Setup headers
    local headers = {}
    local col1_label = targetLabel or "Target"
    local col2_label = valueLabel or "Value"
    local col3_label = "Description"
    
    -- Set column order
    if targetFirst == "true" or targetFirst == true then
      table.insert(headers, create_cell(col1_label))
      table.insert(headers, create_cell(col2_label))
    else
      table.insert(headers, create_cell(col2_label))
      table.insert(headers, create_cell(col1_label))
    end
    
    -- Process rows
    local rows = {}
    local include_desc = false
    
    for i, item in ipairs(dl.content) do
      local row = {}
      
      -- Get term and definition parts
      local term = item[1] or {}  -- Term (usually inlines)
      local defs = item[2] or {}  -- Definitions (usually blocks)
      
      -- Extract target/value attributes or text
      local target_val = extract_deep_attributes(item, "target") or extract_text(term) or ""
      local value_val = extract_deep_attributes(item, "value") or ""
      
      -- If no explicit value, use term as value
      if value_val == "" then
        value_val = extract_text(term)
      end
      
      -- Create row in correct order
      if targetFirst == "true" or targetFirst == true then
        table.insert(row, create_cell(target_val))
        table.insert(row, create_cell(value_val))
      else
        table.insert(row, create_cell(value_val))
        table.insert(row, create_cell(target_val))
      end
      
      -- Add description if available
      if defs and #defs > 0 then
        include_desc = true
        table.insert(row, defs[1] or create_cell(""))
      end
      
      table.insert(rows, row)
    end
    
    -- Add description header if needed
    if include_desc and #headers < 3 then
      table.insert(headers, create_cell(col3_label))
    end
    
    if #rows > 0 then
      return create_table(nil, headers, rows)
    end
  end
  
  return dl
end

-- Convert BulletList to table when it has YAGS attributes
function BulletList(bl)
  debug("Processing BulletList with " .. #bl.content .. " items")
  
  -- Check for YAGS itemlist attributes
  local order = extract_deep_attributes(bl, "order")
  local name = extract_deep_attributes(bl, "name")
  
  -- This is a YAGS formatted list if it has order attribute
  if order then
    debug("Found YAGS itemlist in BulletList with order=" .. order)
    
    -- Setup headers based on list type
    local headers = {}
    if order == "strict" or order == "sort" then
      table.insert(headers, create_cell("Item"))
      table.insert(headers, create_cell("Description"))
    else
      table.insert(headers, create_cell("Item"))
      table.insert(headers, create_cell("Value"))
    end
    
    -- Process rows
    local rows = {}
    for i, item in ipairs(bl.content) do
      local row = {}
      
      -- Extract name/value attributes
      local name_val = extract_deep_attributes(item, "name") or tostring(i)
      
      -- Add columns
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

-- Convert OrderedList to table when it matches YAGS format
function OrderedList(ol)
  debug("Processing OrderedList with " .. #ol.content .. " items")
  
  -- Check for YAGS attributes
  local order = extract_deep_attributes(ol, "order")
  
  if order == "1" or order == "sort" or order == "strict" then
    debug("Found YAGS ordered list")
    
    -- Setup headers
    local headers = {
      create_cell("Number"),
      create_cell("Description")
    }
    
    -- Process rows
    local rows = {}
    for i, item in ipairs(ol.content) do
      local row = {}
      
      -- Extract item number
      local num_val = extract_deep_attributes(item, "name") or tostring(i)
      
      table.insert(row, create_cell(num_val))
      table.insert(row, item)
      
      table.insert(rows, row)
    end
    
    if #rows > 0 then
      return create_table(nil, headers, rows)
    end
  end
  
  return ol
end

-- Check if a block has targetlist properties and convert if needed
function Block(block)
  debug("Checking Block of type " .. block.t)
  
  -- Check for YAGS targetlist attributes
  local targetFirst = extract_deep_attributes(block, "targetFirst")
  local targetLabel = extract_deep_attributes(block, "targetLabel")
  local valueLabel = extract_deep_attributes(block, "valueLabel")
  
  if targetFirst or targetLabel or valueLabel then
    debug("Found potential YAGS targetlist in Block")
    
    -- If it has a targetlist class, process it directly
    if block.attr and block.attr.classes then
      for _, class in ipairs(block.attr.classes) do
        if class == "targetlist" then
          return process_targetlist(block)
        end
      end
    end
  end
  
  return block
end

-- Return all filter functions
return {
  Div = Div,
  DefinitionList = DefinitionList,
  BulletList = BulletList,
  OrderedList = OrderedList,
  Block = Block
}
