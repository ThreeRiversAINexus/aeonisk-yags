-- Pandoc Lua filter to inspect AST structure for YAGS custom elements

local function table_to_string_simple(tbl)
  if not tbl then return "{}" end
  local parts = {}
  local count = 0
  -- Pandoc attribute objects might need specific iteration or might work with pairs.
  -- Let's assume pairs works due to metamethods.
  for k, v in pairs(tbl) do
    table.insert(parts, tostring(k) .. ": " .. pandoc.utils.stringify(v)) -- Use stringify for Pandoc values
    count = count + 1
  end
  if count == 0 then return "{}" end
  return "{ " .. table.concat(parts, ", ") .. " }"
end

function print_element_info(el_type, el)
  io.stderr:write("LUA_DEBUG: Encountered " .. el_type .. "\n")
  if el.identifier and el.identifier ~= "" then
    io.stderr:write("  ID: " .. el.identifier .. "\n")
  end
  
  local classes_str = table_to_string_simple(el.classes)
  if classes_str ~= "{}" then
    io.stderr:write("  Classes: " .. classes_str .. "\n")
  end
  
  -- el.attr is the primary attribute map (userdata)
  -- el.attributes is an alias to el.attr in recent Pandoc versions
  local attr_str = table_to_string_simple(el.attributes) 
  if attr_str ~= "{}" then
    io.stderr:write("  Attributes: " .. attr_str .. "\n")
  end
  io.stderr:write("----\n")
end

function Div(el)
  print_element_info("Div", el)
  return el
end

function BulletList(el)
  print_element_info("BulletList", el)
  if el.content and el.content[1] then
    local first_list_item_content = el.content[1] 
    if first_list_item_content[1] then 
        io.stderr:write("  First item's first block type: " .. first_list_item_content[1].t .. "\n")
        local item_attr_str = table_to_string_simple(first_list_item_content[1].attributes)
        if item_attr_str ~= "{}" then
             io.stderr:write("  First item's first block attributes: " .. item_attr_str .. "\n")
        end
    end
  end
  io.stderr:write("----\n")
  return el
end

function OrderedList(el)
  print_element_info("OrderedList", el)
  if el.content and el.content[1] then
    local first_list_item_content = el.content[1] 
    if first_list_item_content[1] then 
        io.stderr:write("  First item's first block type: " .. first_list_item_content[1].t .. "\n")
        local item_attr_str = table_to_string_simple(first_list_item_content[1].attributes)
        if item_attr_str ~= "{}" then
             io.stderr:write("  First item's first block attributes: " .. item_attr_str .. "\n")
        end
    end
  end
  io.stderr:write("----\n")
  return el
end

function DefinitionList(el)
  print_element_info("DefinitionList", el)
  if el.content then
    for i, def_item_pair in ipairs(el.content) do
      io.stderr:write("  DefinitionList Item " .. i .. ":\n")
      local term_inlines = def_item_pair[1] -- list of inlines
      local def_blocks_list = def_item_pair[2] -- list of (list of blocks)

      io.stderr:write("    Term (" .. #term_inlines .. " inlines):\n")
      for j, inline_el in ipairs(term_inlines) do
        io.stderr:write("      Term Inline " .. j .. " type: " .. inline_el.t .. "\n")
        local term_inline_attr_str = table_to_string_simple(inline_el.attr)
        if term_inline_attr_str ~= "{}" then
          io.stderr:write("        Term Inline " .. j .. " Attributes: " .. term_inline_attr_str .. "\n")
        end
      end

      -- Optionally, print info about definition blocks if needed later
      -- io.stderr:write("    Definition (" .. #def_blocks_list .. " block lists):\n")
    end
  end
  io.stderr:write("----\n")
  return el
end

-- Fallback for any Block element to see its type
-- This helps catch elements not explicitly handled above.
function Block(el)
    -- Only print if not one of the types we already have a specific function for.
    if el.t ~= "Div" and el.t ~= "BulletList" and el.t ~= "OrderedList" and el.t ~= "DefinitionList" then
        io.stderr:write("LUA_DEBUG_BLOCK: Unhandled Type: " .. el.t .. "\n")
        local attr_str = table_to_string_simple(el.attributes)
        if attr_str ~= "{}" then
             io.stderr:write("  Attributes: " .. attr_str .. "\n")
        end
        io.stderr:write("----\n")
    end
    return el
end
