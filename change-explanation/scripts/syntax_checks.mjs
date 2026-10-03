// Optional browser checks: exercise language detection, scopes, and lossless enhancement.
export async function checkSyntax(evaluate, adapter) {
  const cases = [
    {file:'CLIENT.PY', language:'python', source:'def greet(name):\n    """A multiline\n    greeting."""\n    return "Hello " + name', multiline:'hljs-string', line:2},
    {file:'client.ts', language:'typescript', source:'interface User { name: string }\nconst greet = (user: User): string => `Hello ${user.name}`;'},
    {file:'client.tsx', language:'typescript', source:'const count: number = 42;\nexport function getCount(): number { return count; }'},
    {file:'client.mjs', language:'javascript', source:'/* A multiline\n   comment */\nconst message = `Hello\nworld`;\nexport function greet() { return message; }', multiline:'hljs-comment', line:1},
    {file:'index.html', language:'xml', source:'<style>body { color: red; }</style>\n<script>const answer = 42;</script>\n<div class="welcome">Hello</div>'},
    {file:'styles.css', language:'css', source:'.button { color: #fff; display: flex; }'},
    {file:'styles.scss', language:'scss', source:'$color: #fff;\n.button { color: $color; }'},
    {file:'config.json', language:'json', source:'{ "enabled": true, "count": 42, "name": "example" }'},
    {file:'pipeline.yml', language:'yaml', source:'name: Example\njobs:\n  build:\n    enabled: true'},
    {file:'settings.toml', language:'ini', source:'[server]\nport = 8080\nname = "example"'},
    {file:'query.sql', language:'sql', source:'SELECT name, COUNT(*) FROM users WHERE enabled = true GROUP BY name;'},
    {file:'script.ps1', language:'powershell', source:'$path = "C:\\project\\file.txt"\nGet-Content -LiteralPath $path'},
    {file:'module.psm1', language:'powershell', source:'function Get-Name { param($User) return $User.Name }'},
    {file:'.bashrc', language:'bash', source:'cat <<EOF\nHello $USER\nEOF\nexport PATH="$PATH:/opt/bin"', multiline:'hljs-string', line:1},
    {file:'Dockerfile.prod', language:'dockerfile', source:'FROM python:3.12\nWORKDIR /app\nCOPY . .\nRUN python -m compileall .'},
    {file:'Makefile', language:'makefile', source:'build:\n\tcc -o app main.c'},
    {file:'CMakeLists.txt', language:'cmake', source:'cmake_minimum_required(VERSION 3.20)\nproject(Example)\nadd_executable(app main.c)'},
    {file:'main.c', language:'c', source:'#include <stdio.h>\nint main(void) { printf("hello"); return 0; }'},
    {file:'main.cpp', language:'cpp', source:'#include <iostream>\nint main() { std::cout << "hello"; return 0; }', nested:'.hljs-meta .hljs-keyword'},
    {file:'Main.java', language:'java', source:'public class Main { public static void main(String[] args) { System.out.println("Hello"); } }'},
    {file:'Program.cs', language:'csharp', source:'using System;\nclass Program { static void Main() { Console.WriteLine("Hello"); } }'},
    {file:'main.go', language:'go', source:'package main\nimport "fmt"\nfunc main() { fmt.Println("hello") }'},
    {file:'main.rs', language:'rust', source:'fn main() { let count: u32 = 42; println!("{}", count); }'},
    {file:'Main.kt', language:'kotlin', source:'fun main() { val name = "World"; println("Hello $name") }'},
    {file:'App.swift', language:'swift', source:'import Foundation\nlet message: String = "Hello"\nprint(message)'},
    {file:'main.dart', language:'dart', source:'void main() { final message = "Hello"; print(message); }'},
    {file:'Gemfile', language:'ruby', source:'source "https://rubygems.org"\ngem "rake"'},
    {file:'main.ex', language:'elixir', source:'defmodule Main do\n  def greet(name), do: "Hello #{name}"\nend'},
    {file:'main.lua', language:'lua', source:'local name = "World"\nfunction greet() return "Hello " .. name end'},
    {file:'main.php', language:'php', source:'<?php\nfunction greet($name) { return "Hello " . $name; }'},
    {file:'main.tf', language:'terraform', source:'resource "aws_instance" "web" {\n  ami = "ami-example"\n}'},
    {file:'query.graphql', language:'graphql', source:'query GetUser($id: ID!) { user(id: $id) { name email } }'},
    {file:'README.md', language:'markdown', source:'# Example\n\nA **small** example with `code`.'},
    {file:'schema.proto', language:'protobuf', source:'syntax = "proto3";\nmessage User { string name = 1; }'},
    {explicit:'Python', file:'wrong.js', language:'python', source:'def greet(name):\n    return "Hello " + name'},
    {explicit:'C#', language:'csharp', source:'public class User { public string Name { get; set; } }'},
    {explicit:'text', file:'script.py', language:'plaintext', source:'def greet(): return "Hello"', plain:true},
    {explicit:'unknown-language', file:'script.py', language:'plaintext', source:'def greet(): return "Hello"', plain:true},
    {language:'python', source:'from pathlib import Path\n\ndef read_file(path):\n    with Path(path).open() as stream:\n        return stream.read()'},
    {language:'sql', source:'SELECT users.name, COUNT(orders.id) FROM users LEFT JOIN orders ON users.id = orders.user_id GROUP BY users.name ORDER BY users.name;'},
    {language:'plaintext', source:'hello world', plain:true},
    {explicit:'javascript', language:'javascript', source:'const value = "<script>window.bad = true</script><img src=x onerror=bad()>";\n\nconst next = 2;'},
    {file:'empty.py', language:'python', before:'def previous():\n    return "previous"', source:''}
  ];
  if (!await evaluate('!!globalThis.ChangeExplanationHLJS')) return null;
  const initial = await evaluate(`(() => ({
    blocks: [...document.querySelectorAll('.code-change')].map(block => ({language:block.dataset.resolvedLanguage, highlighted:block.dataset.highlighted})),
    recipes: [...document.querySelectorAll('.recipe-json code')].map(code => ({text:code.textContent, highlighted:code.dataset.highlighted}))
  }))()`);
  await evaluate(`(() => {
    const cases = ${JSON.stringify(cases)}, container = document.createElement('div');
    container.id = 'syntax-fixtures';
    container.hidden = true;
    for (const fixture of cases) {
      const block = document.createElement('div');
      block.className = 'code-change';
      block.dataset.file = fixture.file || '';
      block.dataset.language = fixture.explicit || '';
      const badge = document.createElement('span');
      badge.className = 'code-language';
      block.append(badge);
      for (const source of [fixture.before ?? fixture.source, fixture.source]) {
        const excerpt = document.createElement('pre');
        excerpt.className = 'code-excerpt';
        if (source) source.split('\\n').forEach((text, index) => {
          const row = document.createElement('span');
          row.className = 'code-line ' + (index ? 'context' : 'added');
          for (const [className, value] of [['code-lineno',String(40+index)],['code-sign',index?' ':'+'],['code-text',text]]) {
            const span = document.createElement('span');
            span.className = className;
            span.textContent = value;
            row.append(span);
          }
          excerpt.append(row);
        });
        block.append(excerpt);
      }
      container.append(block);
    }
    document.body.append(container);
  })()`);
  await evaluate(adapter);
  const checked = await evaluate(`(() => {
    const cases = ${JSON.stringify(cases)}, failures = [], samples = [];
    const blocks = [...document.querySelectorAll('#syntax-fixtures .code-change')];
    blocks.forEach((block, index) => {
      const fixture = cases[index], language = block.dataset.resolvedLanguage;
      const tokens = block.querySelectorAll('[class*="hljs-"]');
      const before = [...block.querySelectorAll('.code-excerpt')][0];
      const lines = [...before.querySelectorAll('.code-text')];
      samples.push({file:fixture.file || null, explicit:fixture.explicit || null, expected:fixture.language, detected:language, tokens:tokens.length});
      if (language !== fixture.language) failures.push('Language: ' + JSON.stringify(samples.at(-1)));
      if (fixture.plain ? tokens.length !== 0 : tokens.length === 0) failures.push('Token scopes: ' + index);
      const expected = fixture.before ?? fixture.source;
      if (lines.map(line=>line.textContent).join('\\n') !== expected) failures.push('Source changed: ' + index);
      if (fixture.multiline && !lines[fixture.line]?.querySelector('.'+fixture.multiline)) failures.push('Lost multiline scope: ' + index);
      if (fixture.nested && !before.querySelector(fixture.nested)) failures.push('Lost nested scope: ' + index);
      if ([...before.querySelectorAll('.code-lineno')].some((node,i)=>node.textContent!==String(40+i))) failures.push('Line numbers changed: ' + index);
      if ([...before.querySelectorAll('.code-sign')].some((node,i)=>node.textContent!==(i?' ':'+'))) failures.push('Diff signs changed: ' + index);
      if (block.querySelector('img,script')) failures.push('Executable source injected: ' + index);
    });
    document.getElementById('syntax-fixtures').remove();
    return {samples, failures, languages:globalThis.ChangeExplanationHLJS.default.listLanguages().length};
  })()`);
  for (const block of initial.blocks) {
    if (!block.language || block.highlighted !== 'true') checked.failures.push('A rendered excerpt was not enhanced.');
  }
  for (const recipe of initial.recipes) {
    JSON.parse(recipe.text);
    if (recipe.highlighted !== 'true') checked.failures.push('A JSON recipe was not enhanced.');
  }
  const after = await evaluate(`Array.from(document.querySelectorAll('.recipe-json code'), code => code.textContent)`);
  if (JSON.stringify(after) !== JSON.stringify(initial.recipes.map(recipe=>recipe.text))) checked.failures.push('Recipe text changed on repeat enhancement.');
  if (checked.failures.length) throw new Error('Syntax checks failed: ' + checked.failures.join('; '));
  return {...checked, recipes:initial.recipes.length, excerpts:initial.blocks.length};
}
