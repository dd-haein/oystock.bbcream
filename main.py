import asyncio
import re
import os
import random
import requests
from playwright.async_api import async_playwright
# 특정 이름을 가져오지 않고 라이브러리 전체를 가져옵니다 (ImportError 방지)
import playwright_stealth

print("🎬 [시스템 시작] Stealth 모드 로드 방식을 변경하여 재시도합니다...")

TARGET_URL = os.environ.get("TARGET_URL")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

async def get_inventory():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            languages=["ko-KR", "ko"]
        )
        
        page = await context.new_page()
        
        # --- 수정된 Stealth 적용 방식 ---
        # 라이브러리 내부의 stealth_async 함수를 직접 호출합니다.
        await playwright_stealth.stealth_async(page)
        
        results = []
        try:
            if not TARGET_URL:
                print("❌ 에러: TARGET_URL이 설정되지 않았습니다.")
                return ["URL 설정 오류"]

            print(f"🔍 페이지 접속 중: {TARGET_URL}")
            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=90000)
            
            print("⏳ 보안 확인 중... (10초 대기)")
            await page.wait_for_timeout(10000)

            title = await page.title()
            print(f"📄 현재 페이지 제목: {title}")
            
            # Cloudflare 차단 여부 체크
            if "잠시만" in title or "Cloudflare" in title or "Just a moment" in title:
                print("❌ 보안 장벽을 넘지 못했습니다. GitHub IP가 차단된 상태일 수 있습니다.")
                return ["Cloudflare 보안 장벽 우회 실패"]

            # --- 이후 재고 확인 로직 (동일) ---
            opt_btn_sel = 'button:has-text("선택"), button[class*="OptionSelector_btn-option"]'
            try:
                await page.wait_for_selector(opt_btn_sel, timeout=15000)
            except:
                print("❌ 옵션 버튼 미발견")
                return ["페이지 로딩 실패 (옵션 버튼 없음)"]

            await page.click(opt_btn_sel)
            await page.wait_for_selector('li[class*="OptionSelector_option-item"]', state="visible", timeout=10000)
            
            items = await page.locator('li[class*="OptionSelector_option-item"]').all()
            total_count = len(items)
            print(f"📦 총 {total_count}개의 옵션 발견")

            for i in range(total_count):
                if not await page.locator('li[class*="OptionSelector_option-item"]').first.is_visible():
                    await page.click(opt_btn_sel)
                    await page.wait_for_timeout(1000)

                current_items = await page.locator('li[class*="OptionSelector_option-item"]').all()
                target = current_items[i]
                opt_name = (await target.locator('span[class*="option-item-tit"]').inner_text()).strip()
                print(f"🔄 [{i+1}/{total_count}] {opt_name} 확인 중...")

                class_attr = await target.get_attribute("class") or ""
                if "is-soldout" in class_attr:
                    results.append(f"{opt_name} : 품절")
                    continue

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
                    except: pass
                    
                    results.append(f"{opt_name} : {stock}")
                    print(f"✅ {opt_name} : {stock}")
                    
                    del_btn = page.locator('button[class*="OptionSelector_btn-delete"]').first
                    if await del_btn.is_visible():
                        await del_btn.click()
                        await page.wait_for_timeout(1000)
                else:
                    results.append(f"{opt_name} : 수량 확인 불가")

            return results

        except Exception as e:
            print(f"🚨 에러 발생: {e}")
            return results if results else [f"실행 중 에러: {str(e)}"]
        finally:
            await browser.close()

def send_slack(msg_list):
    if not msg_list or not SLACK_WEBHOOK_URL: return
    report = "\n".join([f"• {m}" for m in msg_list])
    payload = {"text": f"📊 *올리브영 실시간 재고 리포트 (Stealth)*\n{report}"}
    requests.post(SLACK_WEBHOOK_URL, json=payload)
    print("📢 슬랙 메시지 전송 완료")

if __name__ == "__main__":
    final_results = asyncio.run(get_inventory())
    send_slack(final_results)
