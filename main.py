import asyncio
import re
import os
import random
import requests
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async  # Stealth 라이브러리 임포트

print("🎬 [시스템 시작] Stealth 모드로 보안 우회를 시도합니다...")

TARGET_URL = os.environ.get("TARGET_URL")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

async def get_inventory():
    async with async_playwright() as p:
        # 브라우저 설정 (더 일반적인 사양으로 변경)
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            languages=["ko-KR", "ko"]
        )
        
        page = await context.new_page()
        
        # --- 핵심: Stealth 스크립트 주입 ---
        await stealth_async(page)
        
        results = []
        try:
            print(f"🔍 페이지 접속 중: {TARGET_URL}")
            # 보안 대기실 통과를 위해 타임아웃을 넉넉히 잡습니다.
            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=90000)
            
            # 대기실 통과를 위해 랜덤하게 조금 더 기다립니다.
            await page.wait_for_timeout(random.randint(5000, 8000))

            # 현재 페이지 제목을 출력하여 대기실에 갇혔는지 확인합니다.
            title = await page.title()
            print(f"📄 현재 페이지 제목: {title}")
            
            if "잠시만 기다려 주세요" in title or "Cloudflare" in title:
                print("❌ 여전히 보안 장벽에 막혀 있습니다.")
                return ["보안 장벽(Cloudflare) 우회 실패"]

            # --- 이후 로직은 동일하지만 안정성 강화 ---
            opt_btn_sel = 'button:has-text("선택"), button[class*="OptionSelector_btn-option"]'
            
            # 버튼이 로딩될 때까지 기다림
            try:
                await page.wait_for_selector(opt_btn_sel, timeout=15000)
            except:
                print("❌ 옵션 버튼 로딩 실패 (대기실을 못 넘었을 확률 높음)")
                return ["페이지 로딩 실패 (옵션 버튼 미발견)"]

            await page.click(opt_btn_sel)
            await page.wait_for_selector('li[class*="OptionSelector_option-item"]', state="visible", timeout=10000)
            
            items = await page.locator('li[class*="OptionSelector_option-item"]').all()
            total_count = len(items)
            print(f"📦 총 {total_count}개의 옵션 발견")
            
            # (인간적인 순회 로직 시작)
            for i in range(total_count):
                # 목록이 닫혔는지 수시로 체크
                if not await page.locator('li[class*="OptionSelector_option-item"]').first.is_visible():
                    await page.click(opt_btn_sel)
                    await page.wait_for_timeout(1000)

                current_items = await page.locator('li[class*="OptionSelector_option-item"]').all()
                target = current_items[i]
                
                opt_name = (await target.locator('span[class*="option-item-tit"]').inner_text()).strip()
                print(f"🔄 [{i+1}/{total_count}] {opt_name} 분석 중...")

                class_attr = await target.get_attribute("class") or ""
                if "is-soldout" in class_attr:
                    results.append(f"{opt_name} : 품절")
                    continue

                # 클릭 및 재고 확인
                await target.click(force=True)
                await page.wait_for_timeout(random.randint(1500, 2500))

                input_sel = 'input[data-qa-name="input-product-number"], input[class*="QuantityCounter_count"]'
                input_field = page.locator(input_sel).first
                
                if await input_field.is_visible():
                    await input_field.fill("999")
                    await page.keyboard.press("Enter")
                    
                    stock = "999+ 예상"
                    try:
                        toast_sel = 'div[class*="Toast_toast-inner"]'
                        await page.wait_for_selector(toast_sel, timeout=4000)
                        toast_text = await page.inner_text(toast_sel)
                        if "재고" in toast_text:
                            match = re.search(r'\d+', toast_text)
                            stock = f"재고 {match.group()}개"
                    except:
                        pass
                    
                    results.append(f"{opt_name} : {stock}")
                    print(f"✅ {opt_name} : {stock}")
                    
                    # 수량창 초기화
                    del_btn = page.locator('button[class*="OptionSelector_btn-delete"]').first
                    if await del_btn.is_visible():
                        await del_btn.click()
                        await page.wait_for_timeout(1000)
                else:
                    results.append(f"{opt_name} : 입력창 미발견")

            return results

        except Exception as e:
            print(f"🚨 중단됨: {e}")
            return results if results else [f"에러 발생: {str(e)}"]
        finally:
            await browser.close()

def send_slack(msg_list):
    if not msg_list or not SLACK_WEBHOOK_URL: return
    report = "\n".join([f"• {m}" for m in msg_list])
    payload = {"text": f"📊 *올리브영 실시간 재고 리포트 (Stealth)*\n{report}"}
    requests.post(SLACK_WEBHOOK_URL, json=payload)

if __name__ == "__main__":
    final_results = asyncio.run(get_inventory())
    send_slack(final_results)
