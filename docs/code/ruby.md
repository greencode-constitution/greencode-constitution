# Ruby Energy Anti-Patterns: Detection & Fix Guide

> Agent skill: scan a Ruby codebase for energy-wasting patterns and apply fixes.

---

## How to Use This Skill

1. Run the **Detect** command for each anti-pattern against the project source tree.
2. Review each match — not every hit is a true positive; use context.
3. Apply the **Fix** pattern, adapting to the surrounding code.

---

## 1. String Concatenation in Loops

**Why it wastes energy**: Ruby strings are mutable, but `+` creates a new string each time. Use `<<` (shovel operator) or `Array#join` instead.

### Detect

```bash
# String += inside loops
grep -rEn '(\.each|\.times|for .* in|while )' -A10 --include="*.rb" ./src | grep -E '\+= *["\x27]'

# String + inside loops
grep -rEn '(\.each|\.times|for .* in|while )' -A10 --include="*.rb" ./src | grep -E '= .* \+ ["\x27]'
```

### Bad

```ruby
result = ""
items.each do |item|
  result += item.to_s + ", "  # new string each iteration
end
```

### Fix

```ruby
# Use shovel operator (mutates in-place, no allocation):
result = ""
items.each do |item|
  result << item.to_s << ", "
end

# Or use join (best):
result = items.join(", ")
```

---

## 2. N+1 Query Problem (Rails)

**Why it wastes energy**: An initial query fetches N rows, then N additional queries fetch related objects one at a time.

### Detect

```bash
# .all or .where followed by .each (potential N+1)
grep -rEn '\.(all|where|find)\b' -A5 --include="*.rb" ./src | grep -E '\.each'

# Missing includes/eager_load/preload
grep -rEn '\.(all|where)\(' --include="*.rb" ./src | grep -v -E '(includes|eager_load|preload|joins)'
```

### Bad

```ruby
users = User.all
users.each do |user|
  puts user.profile.bio  # N extra queries
end
```

### Fix

```ruby
users = User.includes(:profile).all
users.each do |user|
  puts user.profile.bio  # eager loaded, no extra queries
end
```

---

## 3. Database Queries Inside Loops

**Why it wastes energy**: Each query has round-trip overhead. Batch lookups amortize this.

### Detect

```bash
grep -rEn '(\.each|\.times|\.map|\.select)' -A10 --include="*.rb" ./src | grep -E '\.(find|find_by|where|first|last)\('
```

### Bad

```ruby
user_ids.each do |id|
  user = User.find(id)  # one query per iteration
  process(user)
end
```

### Fix

```ruby
users = User.where(id: user_ids)
users.each do |user|
  process(user)
end
```

---

## 4. `include?` on Array in Loops (O(n²))

**Why it wastes energy**: `Array#include?` is O(n). Inside another loop this becomes O(n×m). Use a `Set` for O(1).

### Detect

```bash
grep -rEn '(\.each|for .* in)' -A10 --include="*.rb" ./src | grep -E '\.include\?'
```

### Bad

```ruby
common = []
list1.each do |item|
  common << item if list2.include?(item)  # O(n) per call
end
```

### Fix

```ruby
require 'set'
set2 = list2.to_set
common = list1.select { |item| set2.include?(item) }
```

---

## 5. Object Instantiation in Loops

**Why it wastes energy**: Creating heavy objects (Regexp, formatters) inside loops when they could be created once.

### Detect

```bash
grep -rEn '(\.each|\.times|for .* in|while )' -A10 --include="*.rb" ./src | grep -E '\.new\b|Regexp\.new'
```

### Bad

```ruby
lines.each do |line|
  pattern = Regexp.new('\d+')
  matches = line.scan(pattern)
end
```

### Fix

```ruby
pattern = /\d+/
lines.each do |line|
  matches = line.scan(pattern)
end
```

---

## 6. Not Closing Resources / Missing Block Form

**Why it wastes energy**: Not using the block form of `File.open` risks leaving file handles open on exceptions.

### Detect

```bash
# File.open or File.new without block
grep -rEn 'File\.(open|new)\(' --include="*.rb" ./src | grep -v 'do\b\|{ *|'
```

### Bad

```ruby
f = File.open("data.txt", "r")
content = f.read
f.close  # might not be reached if exception occurs
```

### Fix

```ruby
content = File.read("data.txt")

# Or with block (auto-closes):
File.open("data.txt", "r") do |f|
  content = f.read
end
```

---

## 7. SELECT * in Queries

**Why it wastes energy**: Fetches columns you don't need, wasting bandwidth, memory, and serialization cost.

### Detect

```bash
grep -rEin 'SELECT \*' --include="*.rb" ./src
grep -rEin 'select\(\*\)' --include="*.rb" ./src
```

### Fix

Select only the columns you need:

```ruby
# Bad
users = User.all

# Good (if you only need name and email)
users = User.select(:id, :name, :email).where(active: true)

# Using pluck for raw values:
emails = User.where(active: true).pluck(:email)
```

---

## 8. Repeated Method Calls in Loops

**Why it wastes energy**: Calling `.downcase`, `.upcase`, `.strip` on a value that doesn't change between iterations repeats work.

### Detect

```bash
grep -rEn '(\.each|\.map|\.select)' -A10 --include="*.rb" ./src | grep -E '\.(downcase|upcase|strip|gsub)\b'
```

### Bad

```ruby
names.each do |name|
  if name.downcase == search_term.downcase  # recalculated each iteration
    matches << name
  end
end
```

### Fix

```ruby
search_lower = search_term.downcase
names.each do |name|
  matches << name if name.downcase == search_lower
end
```

---

## 9. `.map` + `.select` / `.reject` (Double Iteration)

**Why it wastes energy**: Chaining creates an intermediate array and iterates twice. A single `each_with_object` or `filter_map` does it in one pass.

### Detect

```bash
grep -rEn '\.map\b.*\.select\b' --include="*.rb" ./src
grep -rEn '\.select\b.*\.map\b' --include="*.rb" ./src
grep -rEn '\.map\b.*\.reject\b' --include="*.rb" ./src
```

### Bad

```ruby
result = items.select { |i| i.active? }.map { |i| i.name }
```

### Fix

```ruby
# Ruby 2.7+ filter_map (single pass):
result = items.filter_map { |i| i.name if i.active? }

# Or each_with_object:
result = items.each_with_object([]) do |i, acc|
  acc << i.name if i.active?
end
```
