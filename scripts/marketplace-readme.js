// 生成插件商店用的 README：去掉 README.md 中 github-only 标记之间的内容。
// 用法：node scripts/marketplace-readme.js，输出到 build/README.md，
// 再由 vsce package --readme-path build/README.md 打包。
const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const src = fs.readFileSync(path.join(root, 'README.md'), 'utf8');

const block = /^<!-- github-only:start.*?-->\r?\n[\s\S]*?^<!-- github-only:end -->\r?\n(\r?\n)?/gm;
const out = src.replace(block, '');

if (/github-only/.test(out)) {
  console.error('README.md 中的 github-only 标记没有成对出现，请检查。');
  process.exit(1);
}

fs.mkdirSync(path.join(root, 'build'), { recursive: true });
fs.writeFileSync(path.join(root, 'build', 'README.md'), out);
console.log(`已生成 build/README.md（去掉 ${src.length - out.length} 个字符）`);
