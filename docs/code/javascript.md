# JavaScript / TypeScript Energy Anti-Patterns: Detection & Fix Guide

> Agent skill: scan a JS/TS codebase for energy-wasting patterns and apply fixes.

---

## How to Use This Skill

1. Run the **Detect** command for each anti-pattern against the project source tree.
2. Review each match — not every hit is a true positive; use context.
3. Apply the **Fix** pattern, adapting to the surrounding code.
4. Detection commands use `--include="*.js" --include="*.ts"` — adjust for `.jsx`, `.tsx`, `.mjs` etc. as needed.

---

## 1. String Concatenation in Loops

**Why it wastes energy**: Repeated `+=` with strings creates new string objects each iteration, causing O(n²) allocations in V8.

### Detect

```bash
# let/var initialized to empty string (setup for loop concat)
grep -rEn 'let.*= *["\x27]{2}' --include="*.js" --include="*.ts" ./src

# += with string literal or template
grep -rEn '\+= *[`"\x27]' --include="*.js" --include="*.ts" ./src
```

### Bad

```javascript
let result = "";
for (const item of items) {
    result += item + ", ";
}
```

### Fix

```javascript
const result = items.join(", ");

// Or if transformation is needed:
const result = items.map(item => transform(item)).join(", ");
```

---

## 2. `.length` Recalculation in `for` Loop Condition

**Why it wastes energy**: The `.length` property is re-read on every iteration. For arrays this is cheap (O(1) property access), but caching it is still a micro-optimization in hot loops and signals intent.

### Detect

```bash
grep -rEn 'for *\(.*;.*\.length' --include="*.js" --include="*.ts" ./src
```

### Bad

```javascript
for (let i = 0; i < array.length; i++) {
    process(array[i]);
}
```

### Fix

```javascript
// Preferred: use for...of
for (const item of array) {
    process(item);
}

// Or cache length if index is needed:
for (let i = 0, len = array.length; i < len; i++) {
    process(array[i]);
}
```

---

## 3. `.includes()` in Loops (O(n²))

**Why it wastes energy**: `Array.includes()` is O(n). Inside another loop this becomes O(n×m). Use a `Set` for O(1) lookups.

### Detect

```bash
grep -rEn '(for|while|forEach)' -A10 --include="*.js" --include="*.ts" ./src | grep -E '\.includes\('
```

### Bad

```javascript
const common = [];
for (const item of list1) {
    if (list2.includes(item)) {
        common.push(item);
    }
}
```

### Fix

```javascript
const set2 = new Set(list2);
const common = list1.filter(item => set2.has(item));
```

---

## 4. Synchronous `fs` Methods

**Why it wastes energy**: `readFileSync`, `writeFileSync`, etc. block the Node.js event loop, preventing any other work from being processed during the I/O wait.

### Detect

```bash
grep -rEn '(readFileSync|writeFileSync|existsSync|mkdirSync|readdirSync|statSync|appendFileSync|copyFileSync|renameSync|unlinkSync)' --include="*.js" --include="*.ts" ./src
```

### Bad

```javascript
const data = fs.readFileSync("config.json", "utf-8");
const parsed = JSON.parse(data);
```

### Fix

```javascript
// Promise-based (Node 10+)
import { readFile } from "fs/promises";
const data = await readFile("config.json", "utf-8");
const parsed = JSON.parse(data);

// Or callback-based
fs.readFile("config.json", "utf-8", (err, data) => {
    if (err) throw err;
    const parsed = JSON.parse(data);
});
```

---

## 5. Creating Functions Inside Loops

**Why it wastes energy**: A new function object (closure) is allocated on every iteration.

### Detect

```bash
grep -rEn '(for|while)' -A10 --include="*.js" --include="*.ts" ./src | grep -E '(function|=>)'
```

### Bad

```javascript
for (let i = 0; i < items.length; i++) {
    items[i].addEventListener("click", function () {
        console.log(i);
    });
}
```

### Fix

```javascript
function handleClick(index) {
    return function () {
        console.log(index);
    };
}
for (let i = 0; i < items.length; i++) {
    items[i].addEventListener("click", handleClick(i));
}
```

---

## 6. Array Spread in Loops

**Why it wastes energy**: `[...arr, newItem]` copies the entire array on every iteration — O(n²) total.

### Detect

```bash
grep -rEn '(for|while)' -A10 --include="*.js" --include="*.ts" ./src | grep -E '\.\.\.'
```

### Bad

```javascript
let result = [];
for (const item of items) {
    result = [...result, transform(item)];  // full copy each time
}
```

### Fix

```javascript
const result = [];
for (const item of items) {
    result.push(transform(item));
}

// Or:
const result = items.map(item => transform(item));
```

---

## 7. Chained `.filter().map()` (Double Iteration)

**Why it wastes energy**: `.filter().map()` iterates the array twice and creates an intermediate array. A single `.reduce()` or a `for` loop does it in one pass.

### Detect

```bash
grep -rEn '\.filter\(.*\.map\(' --include="*.js" --include="*.ts" ./src
grep -rEn '\.map\(.*\.filter\(' --include="*.js" --include="*.ts" ./src
```

### Bad

```javascript
const result = items
    .filter(item => item.active)
    .map(item => item.name);
```

### Fix

```javascript
const result = [];
for (const item of items) {
    if (item.active) {
        result.push(item.name);
    }
}

// Or use .reduce():
const result = items.reduce((acc, item) => {
    if (item.active) acc.push(item.name);
    return acc;
}, []);

// Or use .flatMap() (single pass, no intermediate array):
const result = items.flatMap(item => item.active ? [item.name] : []);
```

**Note**: For small arrays or non-hot paths, `.filter().map()` is perfectly fine for readability. Optimize only when profiling shows this is a bottleneck.

---

## 8. Repeated String Method Calls in Loops

**Why it wastes energy**: Calling `.toUpperCase()`, `.toLowerCase()`, `.trim()`, `.split()` on a value that doesn't change wastes CPU.

### Detect

```bash
grep -rEn '(for|while|forEach)' -A10 --include="*.js" --include="*.ts" ./src | grep -E '\.(toUpperCase|toLowerCase|trim|split)\(\)'
```

### Bad

```javascript
for (const name of names) {
    if (name.toLowerCase() === searchTerm.toLowerCase()) {
        matches.push(name);
    }
}
```

### Fix

```javascript
const searchLower = searchTerm.toLowerCase();
for (const name of names) {
    if (name.toLowerCase() === searchLower) {
        matches.push(name);
    }
}
```

---

## 9. Database Queries Inside Loops (Node.js)

**Why it wastes energy**: Each query has network round-trip overhead. Batch operations amortize this.

### Detect

```bash
grep -rEn '(for|while|forEach)' -A10 --include="*.js" --include="*.ts" ./src | grep -E '(\.find\(|\.findOne\(|\.query\(|await.*Model\.)'
```

### Bad

```javascript
for (const id of userIds) {
    const user = await User.findById(id);
    process(user);
}
```

### Fix

```javascript
const users = await User.find({ _id: { $in: userIds } });
for (const user of users) {
    process(user);
}
```

---

## 10. SELECT * in Queries

**Why it wastes energy**: Fetches columns you don't need, wasting bandwidth, memory, and parsing cost.

### Detect

```bash
grep -rEin 'SELECT \*' --include="*.js" --include="*.ts" ./src
grep -rEn '\.findAll\(|\.getAll\(' --include="*.js" --include="*.ts" ./src
```

### Fix

Select only the fields you need:

```javascript
// Bad
const users = await db.query("SELECT * FROM users WHERE active = true");

// Good
const users = await db.query("SELECT id, name, email FROM users WHERE active = true");

// Mongoose
const users = await User.find({ active: true }).select("name email");
```

---

## 11. Invariant Computation Inside Loops

**Why it wastes energy**: Expressions whose result never changes across iterations are re-evaluated pointlessly.

### Detect

```bash
grep -rEn '(for|while)' -A15 --include="*.js" --include="*.ts" ./src | grep -E '(Math\.(sqrt|pow|sin|cos|log|exp)|new RegExp|JSON\.parse)'
```

### Bad

```javascript
for (let i = 0; i < data.length; i++) {
    const factor = Math.sqrt(baseValue) * Math.PI;
    result[i] = data[i] * factor;
}
```

### Fix

```javascript
const factor = Math.sqrt(baseValue) * Math.PI;
for (let i = 0; i < data.length; i++) {
    result[i] = data[i] * factor;
}
```

---

## 12. Missing HTTP Compression Middleware

**Why it wastes energy**: Serving uncompressed HTTP responses forces more data over the network, wasting bandwidth and energy at every hop. Compression middleware (gzip/brotli) typically reduces payload size by 60-80%.

### Detect

```bash
# Express apps without compression middleware
grep -rEn "app\.use\(|express\(\)" --include="*.js" --include="*.ts" ./src | head -5
grep -rL "compression" --include="*.js" --include="*.ts" ./src | xargs grep -l "express\(\)\|app\.listen"

# Check if compression package is installed
grep -q '"compression"' package.json 2>/dev/null || echo "compression package not in dependencies"

# Next.js / Nuxt without compress config
grep -rEn "compress" --include="next.config.*" --include="nuxt.config.*" .
```

### Bad

```javascript
const express = require("express");
const app = express();
// No compression — all responses sent at full size
app.get("/api/data", (req, res) => {
    res.json(largePayload);
});
```

### Fix

```javascript
const express = require("express");
const compression = require("compression");
const app = express();

app.use(compression()); // gzip/deflate all responses

app.get("/api/data", (req, res) => {
    res.json(largePayload); // now compressed automatically
});
```

---

## 13. Unoptimized Bundle Size (Customer Hardware Impact)

**Why it wastes energy**: Large JavaScript bundles force users to download, parse, and execute more code — draining battery on mobile devices and forcing hardware upgrades. Bloated bundles also increase server egress energy.

### Detect

```bash
# Check for wildcard imports (pulls in entire library)
grep -rEn "import .* from ['\"]lodash['\"]" --include="*.js" --include="*.ts" --include="*.tsx" ./src
grep -rEn "import .* from ['\"]moment['\"]" --include="*.js" --include="*.ts" --include="*.tsx" ./src

# Check for missing code splitting (no dynamic imports)
grep -rL "import\(" --include="*.js" --include="*.ts" --include="*.tsx" ./src | xargs grep -l "import .* from"

# Check bundle analysis config
grep -rEn "webpack-bundle-analyzer\|@next/bundle-analyzer\|rollup-plugin-visualizer" package.json

# Check browserslist for excessive backwards compatibility
grep -rEn "browserslist\|targets" package.json .browserslistrc babel.config.* 2>/dev/null
```

### Bad

```javascript
import _ from "lodash";               // imports entire 71KB library
import moment from "moment";           // imports 67KB + locale data
import { Button } from "antd";         // may import full component library
```

### Fix

```javascript
import groupBy from "lodash/groupBy";  // imports only ~1KB
import dayjs from "dayjs";             // 2KB alternative to moment
import Button from "antd/es/button";   // tree-shakeable import

// Use dynamic imports for code splitting:
const HeavyChart = React.lazy(() => import("./HeavyChart"));
```
