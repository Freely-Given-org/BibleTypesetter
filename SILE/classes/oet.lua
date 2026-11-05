-- A register-set diglot. All distances are PDF points, measured from the trim.
-- Both columns use the same row index. A row owns its note calls, so the page
-- break can be chosen after measuring the complete apparatus for either side.
local class = pl.class(require("classes.base"))
class._name = "oet"
local inside, outside, gutter = 43, 33, 16
local grid, firstY, bottomMargin = 12.5, 77, 31
local rowsPerPage
local boxWidth, clearance = 88, 6
local number, noteNumber = 0, 0
local pageStarted = false
local books = {}
local pagefile, bookPages
local width, column
local version, paired, leftRole
local editionLabels = { rv = "READERS’ VERSION", lv = "LITERAL VERSION" }
local editionTitles = { OET = "Parallel reading edition", ["OET-RV"] = "Readers’ Version", ["OET-LV"] = "Literal Version" }
local serif, sans = "Gentium Plus", "Lato"
local styles = {
   rv = { serif, 10.4 }, lv = { serif, 9.8 }, heading = { sans, 8.5, 700 },
   verse = { sans, 6.9, 700 }, call = { sans, 6.0, 700 },
   note = { serif, 8.9 }, key = { sans, 7.5, 700 },
   absence = { serif, 9.3, 400, "italic" },
   label = { sans, 8.3, 700 }, running = { serif, 10, 400, "italic" },
   title = { serif, 29 }, subtitle = { serif, 13, 400, "italic" },
   intro = { serif, 11.1 }, subhead = { sans, 10, 700 }, outline = { serif, 10.4 },
   copyright = { serif, 9.3 }, colophon = { sans, 7.5 },
}
local fonts, cache = {}, {}

local function fragment (s, role, flags)
   flags = flags or ""
   local id = role .. ":" .. flags
   if s == "◘" then id = id .. ":symbol" end
   if not fonts[id] then
      local spec = styles[role]
      local size, weight, style = spec[2], spec[3] or 400, spec[4] or "normal"
      local rise, gray = 0, 0
      if flags:find("nd") or flags:find("bd") then weight = 700 end
      if flags:find("em") or flags:find("it") or flags:find("bk") or flags:find("ior") then style = "italic" end
      if flags:find("add") then gray = 0.30 end
      if flags:find("untr") then gray, size = 0.40, size * 0.82 end
      if flags:find("sup") then rise, size = 3, size * 0.72 end
      if role == "call" then rise = 3.4 end
      if role == "verse" then rise = 1.0 end
      local family = flags:find("wh") and "Ezra SIL" or ((s == "◘" or flags:find("zsymbol")) and "DejaVu Sans" or spec[1])
      fonts[id] = { options = SILE.font.loadDefaults({
         family = family, size = size, weight = weight, style = style,
         language = flags:find("wh") and "he" or "en", direction = flags:find("wh") and "RTL" or "LTR", script = flags:find("wh") and "Hebr" or "Latn", features = flags:find("sc") and "-liga;-clig;+smcp" or "-liga;-clig",
      }), gray = gray, rise = rise, strike = flags:find("untr") and size * 0.25 }
      cache[id] = {}
   end
   if not cache[id][s] then
      local font = fonts[id]
      local items = SILE.shaper:shapeToken(s, font.options)
      for _, item in ipairs(items) do
         if item.gid == 0 then error("Missing glyph in " .. font.options.family .. ": " .. s) end
      end
      local node = SILE.shaper:formNnode(items, s, font.options).nodes[1]
      cache[id][s] = { value = node.value, w = node.width:tonumber(), font = font, text = s, role = role, flags = flags }
   end
   return cache[id][s]
end

local function paint (part, x, y)
   local out, font = SILE.outputter, part.font
   y = y - font.rise
   out:pushColor({ l = font.gray })
   out:setFont(font.options)
   out:setCursor(x, y)
   out:drawHbox(part.value, part.w)
   if font.strike then out:drawRule(x, y - font.strike, part.w, 0.38) end
   out:popColor()
end

local function label (text, role, x, y, right)
   local part = fragment(text, role)
   paint(part, right and x - part.w or x, y)
end

local function rule (x, y, w, h)
   SILE.outputter:pushColor({ l = 0.48 })
   SILE.outputter:drawRule(x, y, w, h)
   SILE.outputter:popColor()
end

-- A word may contain several adjacent runs (e.g. "of_" + a sacred name).
-- Store note calls on that same word until its line and page are known.
local function append (words, s, role, flags)
   for spaces, token in s:gmatch("(%s*)(%S+)") do
      local spaced = words.space or spaces ~= ""
      local closingQuote = #words > 0 and (token == "”" or token == "’")
      if #words == 0 or (spaced and not closingQuote) then
         words[#words + 1] = { w = 0, ref = words.ref, notes = {} }
      end
      -- Retain the source space but keep a standalone closing quote with its text.
      if closingQuote and spaced then token = " " .. token end
      local word = words[#words]
      local part = fragment(token, role, flags)
      word[#word + 1] = part
      word.w = word.w + part.w
      words.space = false
   end
   if s:find("%s$") then words.space = true end
end

local function splitWord (word, available)
   local first = { w = 0, ref = word.ref, notes = {} }
   local rest = { w = 0, ref = word.ref, notes = word.notes, joined = true }
   local full = false
   for _, part in ipairs(word) do
      if full then rest[#rest + 1] = part; rest.w = rest.w + part.w
      elseif first.w + part.w <= available then first[#first + 1] = part; first.w = first.w + part.w
      else
         local cut, preferred = 0, 0
         for position, code in utf8.codes(part.text) do
            local stop = position + #utf8.char(code) - 1
            if first.w + fragment(part.text:sub(1, stop), part.role, part.flags).w > available then break end
            cut = stop
            if code == 47 or code == 95 or code == 45 then preferred = stop end
         end
         if preferred > 0 then cut = preferred end
         if cut > 0 then
            local prefix = fragment(part.text:sub(1, cut), part.role, part.flags)
            first[#first + 1] = prefix; first.w = first.w + prefix.w
         end
         local suffix = fragment(part.text:sub(cut + 1), part.role, part.flags)
         rest[#rest + 1] = suffix; rest.w = rest.w + suffix.w
         full = true
      end
   end
   assert(#first > 0, "A glyph cannot fit in the text measure")
   return first, rest
end

local function wrap (words, measure, role, indent, startRow)
   local lines, i = {}, 1
   local space = fragment(" ", role).w
   while i <= #words do
      local inset = #lines == 0 and indent or 0
      local available = measure(startRow + #lines) - inset
      local line = { x = inset, gap = space, notes = {} }
      local used = 0
      repeat
         local word = words[i]
         local advance = word.w + ((#line == 0 or word.joined) and 0 or space)
         if #line > 0 and used + advance > available then break end
         if word.w > available + 0.02 then
            local rest
            word, rest = splitWord(word, available)
            words[i] = word
            table.insert(words, i + 1, rest)
            advance = word.w
         end
         line[#line + 1] = word
         for _, note in ipairs(word.notes) do line.notes[#line.notes + 1] = note end
         used, i = used + advance, i + 1
      until i > #words
      if i <= #words and #line > 1 and (role == "rv" or role == "lv") then
         -- Keep lines ragged where justification would open distracting rivers.
         line.gap = space + math.min(1.0, (available - used) / (#line - 1))
      end
      lines[#lines + 1] = line
   end
   return lines
end

local function drawLine (line, x, y)
   x = x + line.x
   for i, word in ipairs(line) do
      for _, part in ipairs(word) do
         paint(part, x, y)
         x = x + part.w
      end
      x = x + ((line[i + 1] and line[i + 1].joined) and 0 or line.gap)
   end
end

local function fixed (w)
   return function () return w end
end

local function addRuns (words, node, role)
   for _, run in ipairs(node) do
      if run.command == "run" then
         append(words, run[1], role, run.options.style)
      elseif run.command == "note" then
         noteNumber = noteNumber + 1
         local id, opts = tostring(noteNumber), run.options
         local note = {}
         append(note, id .. " " .. opts.edition .. " " .. opts.ref .. " · " .. opts.kind .. "  ", "key")
         for _, part in ipairs(run) do append(note, part[1], "note", part.options.style) end
         append(words, id, "call")
         local calls = words[#words].notes
         local lines = wrap(note, fixed(width), "note", 0, 1)
         for index, line in ipairs(lines) do
            line.note, line.noteLine = noteNumber, index
         end
         calls[#calls + 1] = lines
      else
         error("Unknown inline element " .. tostring(run.command))
      end
   end
end

local function headingBox (heading)
   local words, bw = {}, boxWidth
   addRuns(words, heading, "heading")
   for _, word in ipairs(words) do bw = math.max(bw, math.min(column - 55, word.w + 10)) end
   return wrap(words, fixed(bw - 10), "heading", 0, 1), bw
end

local function columnLines (blocks, measure, role)
   -- Summarize a whole missing parallel passage once. Isolated omissions
   -- inside a translated passage retain the original verse position.
   local absent = #blocks > 0
   for _, block in ipairs(blocks) do
      if #block > 0 then
         absent = false
         break
      end
   end
   if absent and role == "lv" then
      local first, last = blocks[1].options.ref, blocks[#blocks].options.ref
      local address = first
      if first ~= last then
         local chapter, verse = last:match("^(%d+):(.+)$")
         address = first .. "–" .. (first:match("^(%d+):") == chapter and verse or last)
      end
      local words = { ref = first }
      append(words, address .. "  No text in the Literal Version.", "absence")
      words[#words].ref = last
      return wrap(words, measure, "absence", 0, 1)
   end
   local lines, words, indent, boxes = {}, {}, 0, {}
   local function available (row)
      return measure(row) - (boxes[row] and boxes[row].bw + clearance or 0)
   end
   local function finish ()
      for _, line in ipairs(wrap(words, available, role, indent, #lines + 1)) do
         lines[#lines + 1] = line
      end
      words = {}
   end
   for _, block in ipairs(blocks) do
      local opts = block.options
      if block.command == "heading" then
         finish()
         while boxes[#lines + 1] do lines[#lines + 1] = { x = 0, gap = 0, notes = {} } end
         local box, bw = headingBox(block)
         for r, line in ipairs(box) do
            boxes[#lines + r] = { line = line, bw = bw, height = r == 1 and #box or nil, keep = r < math.max(#box, 2) }
         end
      else
      if opts.para ~= "" then
         finish()
         local depth = tonumber(opts.para:match("%d$")) or 1
         indent = (opts.para == "nb" or opts.para == "m") and 0 or 7 * depth
      end
      words.space, words.ref = true, opts.ref
      if opts.verse then
         local chapter = opts["chapter-label"] or opts.ref:match("^(%d+):")
         local address = (opts["chapter-start"] == "true" or opts.verse == "1") and chapter .. ":" .. opts.verse or opts.verse
         append(words, address:gsub("-", "–") .. " ", "verse")
         -- A narrow space is part of the same word, keeping the number with text.
      end
      if #block == 0 and opts.verse then append(words, "◘", role) end
      addRuns(words, block, role)
      end
   end
   finish()
   while boxes[#lines + 1] do lines[#lines + 1] = { x = 0, gap = 0, notes = {} } end
   return lines, boxes
end

local function sectionRows (section)
   local heading, rv, lv
   for _, child in ipairs(section) do
      if child.command == "heading" then heading = child
      elseif child.command == "rv" then rv = child
      elseif child.command == "lv" then lv = child end
   end
   local box, boxRows, bw = {}, 0, boxWidth
   if heading then
      box, bw = headingBox(heading)
      boxRows = #box
   end
   local left, innerBoxes = columnLines(rv or lv, function (r) return r <= boxRows and column - bw - clearance or column end, leftRole)
   local right = paired and columnLines(lv, fixed(column), "lv") or {}
   local rows = {}
   for r = 1, math.max(#left, #right, boxRows) do
      local row = { left = left[r], right = right[r], box = box[r], bw = bw, notes = {} }
      -- A page may break only after the entire heading box and its first two
      -- body rows have landed, including any notes called from those rows.
      row.keep = r < math.max(boxRows, 2)
      if r == 1 and boxRows > 0 then row.boxRows = boxRows end
      if innerBoxes and innerBoxes[r] then
         local inner = innerBoxes[r]
         row.box, row.bw, row.boxRows, row.keep = inner.line, inner.bw, inner.height, inner.keep
      end
      for _, field in ipairs({ "box", "left", "right" }) do
         for _, note in ipairs(row[field] and row[field].notes or {}) do
            for _, line in ipairs(note) do row.notes[#row.notes + 1] = line end
         end
      end
      rows[#rows + 1] = row
   end
   rows[#rows].keep = false
   return rows
end

local function startPage ()
   if pageStarted then SILE.outputter:newPage() end
   pageStarted = true
   number = number + 1
   return number % 2 == 1 and inside or outside
end

local function openRecto ()
   -- Count the blank verso physically, without printing furniture on it.
   if number % 2 == 1 then startPage() end
end

local function footer (x)
   local y = firstY + (rowsPerPage + 1) * grid
   label(tostring(number), "label", number % 2 == 1 and x + width or x, y, number % 2 == 1)
end

local function pageRange (rows, a, b)
   local lo, hi
   for r = a, b do
      for _, side in ipairs({ "left", "right" }) do
         for _, word in ipairs(rows[r][side] or {}) do
            local c, v, e = word.ref:match("^(%d+):(%d+)[a-z]?%-?(%d*)[a-z]?$")
            local first = tonumber(c) * 1000 + tonumber(v)
            local last = tonumber(c) * 1000 + tonumber(e ~= "" and e or v)
            lo, hi = math.min(lo or first, first), math.max(hi or last, last)
         end
      end
   end
   local function ref (n) return math.floor(n / 1000) .. ":" .. n % 1000 end
   return lo == hi and ref(lo) or ref(lo) .. " – " .. ref(hi)
end

local function renderBody (rows, name)
   local a = 1
   while a <= #rows do
      local count, b = 0, nil
      for i = a, #rows do
         count = count + #rows[i].notes
         if i - a + 1 + count + (count > 0 and 1 or 0) > rowsPerPage then break end
         if not rows[i].keep then b = i end
      end
      assert(b, "Heading or note cannot fit on a page in " .. name)
      local x = startPage()
      local right = x + column + gutter
      label(name, "running", x, 31)
      label(pageRange(rows, a, b), "running", x + width, 31, true)
      rule(x, 38, width, 0.45)
      label(editionLabels[leftRole], "label", x, firstY - 1.5 * grid)
      if paired then label(editionLabels.lv, "label", right, firstY - 1.5 * grid) end
      local notes = {}
      for i = a, b do
         local row = rows[i]
         local y = firstY + (i - a) * grid
         if row.left then drawLine(row.left, x, y) end
         if row.right then drawLine(row.right, right, y) end
         local bx = x + column - row.bw
         if row.boxRows then
            local top, h = y - 9.4, row.boxRows * grid
            rule(bx, top, row.bw, 0.4)
            rule(bx, top + h, row.bw, 0.4)
            rule(bx, top, 0.4, h)
            rule(bx + row.bw - 0.4, top, 0.4, h)
         end
         if row.box then drawLine(row.box, bx + 5, y) end
         for _, line in ipairs(row.notes) do notes[#notes + 1] = line end
      end
      -- A call at the bottom of a heading box may follow a body call with a
      -- higher number. Keep the apparatus in numeric order on this page.
      table.sort(notes, function (a, b)
         if a.note == b.note then return a.noteLine < b.noteLine end
         return a.note < b.note
      end)
      local noteY = firstY + (rowsPerPage - #notes) * grid
      if #notes > 0 then rule(x, noteY - 9.5, 40, 0.6) end
      for i, line in ipairs(notes) do drawLine(line, x, noteY + (i - 1) * grid) end
      footer(x)
      a = b + 1
   end
end

local function frontMatter (book, opts, preface)
   local x, y
   local pageNotes = {}
   local function finishPage ()
      if #pageNotes == 0 then return end
      local noteY = firstY + (rowsPerPage - #pageNotes) * grid
      rule(x, noteY - 9.5, 40, 0.6)
      for i, line in ipairs(pageNotes) do drawLine(line, x, noteY + (i - 1) * grid) end
      pageNotes = {}
   end
   local function newPage ()
      finishPage()
      x, y = startPage(), firstY
      label(preface == "copyright" and "Copyright and licence" or "OPEN ENGLISH TRANSLATION", "label", x, 31)
      label(editionTitles[version], "running", x + width, 31, true)
      rule(x, 38, width, 0.45)
      footer(x)
   end
   newPage()
   for _, node in ipairs(book) do
      if node.command ~= "section" then
         local kind = node.options.kind
         local role, before, after = preface == "copyright" and "copyright" or (preface and "outline" or "intro"), 0, 0
         if kind == "mt1" then role, before, after = "title", 1, 1
         elseif node.command == "title" then role = "subtitle"
         elseif kind == "is1" or kind == "is2" or kind == "iot" then role, before = "subhead", 1
         elseif kind == "io1" or kind == "io2" then role, after = "outline", 0 end
         if preface and (kind == "p" or kind == "m" or kind == "b") then before = 1 end
         if preface == "copyright" then after = 1 end
         local words = {}
         addRuns(words, node, role)
         local indent = preface == "copyright" and 0 or (kind == "li1" and 12 or kind == "li2" and 24 or kind == "io2" and 14 or kind == "ip" and 9 or 0)
         local lines = wrap(words, fixed(width - indent), role, 0, 1)
         y = y + before * grid
         if y + math.min(#lines, 2) * grid > firstY + (rowsPerPage - 1) * grid then newPage() end
         for _, line in ipairs(lines) do
            local addedNotes = {}
            for _, note in ipairs(line.notes) do
               for _, noteLine in ipairs(note) do addedNotes[#addedNotes + 1] = noteLine end
            end
            local function limit ()
               local n = #pageNotes + #addedNotes
               return firstY + (rowsPerPage - 1 - n - (n > 0 and 1 or 0)) * grid
            end
            if y > limit() then newPage() end
            assert(y <= limit(), "Introduction note cannot fit on a page in " .. opts.name)
            for _, noteLine in ipairs(addedNotes) do pageNotes[#pageNotes + 1] = noteLine end
            drawLine(line, x + indent, y)
            y = y + (role == "title" and 2 or 1) * grid
         end
         y = y + after * grid
      end
   end
   if preface then finishPage(); return end
   local credits = {
      "Lighter type marks additions. Underscores join parts of a single source word.",
      "Struck words are untranslated. The ◘ sign marks a verse with no text.",
      opts["draft-credit"] or "Open English Translation · Translation draft (version unavailable) · OET.Bible",
      "CC BY-SA 4.0  ·  creativecommons.org/licenses/by-sa/4.0/",
   }
   if opts.credit and opts.credit ~= "" then credits[#credits + 1] = opts.credit end
   local creditLines = {}
   for _, text in ipairs(credits) do
      local words = {}
      append(words, text, "note")
      for _, line in ipairs(wrap(words, fixed(width), "note", 0, 1)) do
         creditLines[#creditLines + 1] = line
      end
   end
   if y + (#creditLines + #pageNotes + 2) * grid > firstY + rowsPerPage * grid then newPage() end
   y = y + grid
   rule(x, y - grid, 40, 0.6)
   for _, line in ipairs(creditLines) do
      if y > firstY + (rowsPerPage - 1) * grid then newPage() end
      drawLine(line, x, y)
      y = y + grid
   end
   finishPage()
end

local function configure (opts)
      if opts.startpage then number = tonumber(opts.startpage) - 1 end
      version = opts.version or "OET"
      paired = version == "OET"
      leftRole = version == "OET-LV" and "lv" or "rv"
      width = SILE.documentState.paperSize[1] - inside - outside
      column = paired and (width - gutter) / 2 or width
      rowsPerPage = math.floor((SILE.documentState.paperSize[2] - bottomMargin - firstY) / grid) - 1
      assert(column >= 150 and width >= 260, "Paper is too narrow for this edition and its margins")
      assert(rowsPerPage >= 12, "Paper is too short for this layout and its margins")
end

function class:registerCommands ()
   self:registerCommand("publication", function (opts, nodes)
      configure(opts)
      pagefile, bookPages = opts.pagefile, {}
      local x = startPage()
      local y = firstY + 7 * grid
      local function centered (text, role)
         local words = {}; append(words, text, role)
         for _, line in ipairs(wrap(words, fixed(width), role, 0, 1)) do
            local w = math.max(0, (#line - 1) * line.gap)
            for _, word in ipairs(line) do w = w + word.w end
            drawLine(line, x + (width - w) / 2, y)
            y = y + 2.5 * grid
         end
      end
      -- Keep the final phrase together instead of leaving “Bible” alone.
      centered("Open English Translation", "title")
      centered("of the Bible", "title")
      y = y + 2 * grid
      centered(opts.title, "subtitle")
      centered(editionTitles[version], "subtitle")
      centered(opts.order, "outline")
      y = firstY + (rowsPerPage - 5) * grid
      centered("OET.Bible · Freely-Given.org", "note")
      bookPages[#bookPages + 1] = "TITLE\t" .. number
      for _, node in ipairs(nodes) do
         if node.command == "copyright" then
            bookPages[#bookPages + 1] = "COPYRIGHT\t" .. (number + 1)
            frontMatter(node, { name = "Copyright" }, "copyright")
         end
      end
      local function contentsPage ()
         x, y = startPage(), firstY
         label("Contents", "title", x, y); y = y + 3 * grid
         footer(x)
      end
      openRecto()
      bookPages[#bookPages + 1] = "CONTENTS\t" .. (number + 1)
      contentsPage()
      local preface
      for _, node in ipairs(nodes) do
         if node.command == "entry" then
            local words = {}
            append(words, node.options.code == "FRT" and node.options.name or node.options.code .. "   " .. node.options.name, "outline")
            local lines = wrap(words, fixed(width - 45), "outline", 0, 1)
            if y + (#lines - 1) * grid > firstY + (rowsPerPage - 1) * grid then contentsPage() end
            label(node.options.page == "0" and "—" or node.options.page, "outline", x + width, y, true)
            for _, line in ipairs(lines) do drawLine(line, x, y); y = y + grid end
         elseif node.command == "preface" then preface = node end
      end
      openRecto()
      bookPages[#bookPages + 1] = "FRT\t" .. (number + 1)
      frontMatter(preface, { name = "Preface" }, true)
   end)
   self:registerCommand("book", function (opts, book)
      configure(opts)
      if opts.recto == "true" then openRecto() end
      if bookPages then bookPages[#bookPages + 1] = opts.code .. "\t" .. (number + 1) end
      fonts, cache = {}, {}
      noteNumber = 0
      books[#books + 1] = opts.name
      frontMatter(book, opts)
      local rows = {}
      for _, node in ipairs(book) do
         if node.command == "section" then
            for _, row in ipairs(sectionRows(node)) do rows[#rows + 1] = row end
         end
      end
      local endings, count = {}, 0
      for _, side in ipairs(paired and { "rv", "lv" } or { leftRole }) do
         local words = { ref = "1:1" }
         for r = #rows, 1, -1 do
            local line = rows[r].left or rows[r].right
            if line and #line > 0 then words.ref = line[#line].ref; break end
         end
         append(words, opts[side .. "-colophon"] or "", "colophon")
         endings[side] = wrap(words, fixed(column), "colophon", 0, 1)
         count = math.max(count, #endings[side])
      end
      if count > 0 then
         rows[#rows].keep = true
         rows[#rows + 1] = { notes = {}, keep = true, bw = 0 }
         for r = 1, count do
            rows[#rows + 1] = { left = endings[leftRole][r], right = paired and endings.lv[r] or nil,
                               notes = {}, keep = r < count, bw = 0 }
         end
      end
      renderBody(rows, opts.name)
   end)
end

function class:finish ()
   if pagefile then
      local file = assert(io.open(pagefile, "w"))
      file:write(table.concat(bookPages, "\n") .. "\n"); file:close()
   end
   SILE.outputter:setMetadata("Title", "Open English Translation of the Bible · " .. table.concat(books, ", ") .. " · " .. editionTitles[version])
   SILE.outputter:setMetadata("Author", "Open English Translation")
   SILE.outputter:finish()
end

return class
