// Local-only OCR worker. All WASM/language assets resolve inside this project;
// no CDN fallback or uploaded document URL is accepted from an HTTP client.
import { createWorker } from 'tesseract.js';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const input=path.resolve(process.argv[2]);
const output=path.resolve(process.argv[3]);
const languagePath=path.join(root,'runtime','ocr');
for (const language of ['kor','eng']) {
  if (!fs.existsSync(path.join(languagePath,`${language}.traineddata`))) throw new Error('Local OCR language assets missing');
}
// Reject remote fetches rather than letting a missing resource invoke a CDN.
globalThis.fetch=async()=>{throw new Error('Network disabled for document OCR');};
const worker=await createWorker('kor+eng',1,{
  langPath:languagePath,gzip:false,cacheMethod:'none',
  corePath:path.join(root,'node_modules','tesseract.js-core'),
  workerPath:path.join(root,'node_modules','tesseract.js','src','worker-script','node','index.js'),
  logger:()=>{},
});
try {
  const result=await worker.recognize(input);
  fs.writeFileSync(output,JSON.stringify({text:result.data.text,confidence:result.data.confidence,engine:'tesseract.js 6.0.1; kor+eng; local assets'}),'utf8');
} finally {await worker.terminate();}
