import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
auth_file = BASE_DIR / "auth_state_04083941.json"
url_ativ = "https://ava.catolica.edu.br/d2l/le/activities/evaluation/activity/TmpZd05sOHlNREF3WHpFMk9UZzVPQS4xNTUzODg?ou=155388&iteratorRange=all&cft=qe"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 900})
    page = context.new_page()

    page.goto(url_ativ, wait_until="domcontentloaded", timeout=30000)
    time.sleep(6)

    # Inspecionar como os anexos/arquivos são apresentados
    anexos_info = page.evaluate(r"""() => {
        function getAllElements(root) {
            let elements = [];
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
            while (walker.nextNode()) {
                const el = walker.currentNode;
                elements.push(el);
                if (el.shadowRoot) elements = elements.concat(getAllElements(el.shadowRoot));
            }
            return elements;
        }

        const all = getAllElements(document.body);
        const files = [];

        // 1. Elementos com d2l-file-name ou classes de anexo
        for (let el of all) {
            const tag = el.tagName.toLowerCase();
            const cls = (el.className ? el.className.toString() : '').toLowerCase();
            const aria = (el.getAttribute('aria-label') || '').toLowerCase();
            const href = (el.getAttribute('href') || '').toLowerCase();
            const txt = (el.innerText || el.textContent || '').trim();

            if (tag === 'd2l-file-name' || 
                tag === 'd2l-consistent-evaluation-submission-item' ||
                cls.includes('attachment') || 
                cls.includes('file') || 
                aria.includes('baixar o anexo') ||
                href.includes('downloadattachment') ||
                href.includes('download_submission_file')) {
                
                files.push({
                    tag,
                    cls: cls.slice(0, 50),
                    aria: aria.slice(0, 50),
                    href: href.slice(0, 80),
                    txt: txt.slice(0, 80)
                });
            }
        }

        // 2. Contagem por submissões / arquivos
        const subItems = all.filter(el => el.tagName.toLowerCase() === 'd2l-consistent-evaluation-submission-item');
        const fileNames = all.filter(el => el.tagName.toLowerCase() === 'd2l-file-name');
        const linksDownload = all.filter(el => {
            const h = (el.getAttribute('href') || '').toLowerCase();
            const a = (el.getAttribute('aria-label') || '').toLowerCase();
            return h.includes('downloadattachment') || a.includes('baixar o anexo');
        });

        return {
            totalElements: all.length,
            subItemsCount: subItems.length,
            fileNamesCount: fileNames.length,
            fileNamesTexts: fileNames.map(f => (f.innerText || f.textContent || '').trim()),
            linksDownloadCount: linksDownload.length,
            sampleFiles: files.slice(0, 15)
        };
    }""")

    print("\nInformações de Anexos:")
    print(f"  SubItems count: {anexos_info['subItemsCount']}")
    print(f"  FileNames count: {anexos_info['fileNamesCount']}")
    print(f"  FileNames texts: {anexos_info['fileNamesTexts']}")
    print(f"  Links download count: {anexos_info['linksDownloadCount']}")
    print("\nAmostras de elementos de arquivo:")
    for sf in anexos_info['sampleFiles']:
        print("  ", sf)

    browser.close()
