import asyncio
import re
import os
import time
import requests
from playwright.async_api import async_playwright

# 시작 로그
print("🎬 [시스템 시작] 담백한 버전으로 롤백하여 재시도합니다.")

TARGET_URL = os.environ.get("TARGET_URL")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

async def get_inventory():
    async with async_playwright() as p:
        # 브라우저 실행
        browser = await p.chromium.launch(headless=True)
        # 실제 브라우저인 척 최소한의 정보만 설정
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        results = []
        try:
            print(f"🚀 {TARGET_URL} 접속 중...")
            # 1. 페이지 접속
            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            
            # 2. 말씀하신 5~10초 대기 (보안 엔진이 나를 지나치길 기다림)
            print("⏳ 페이지 로딩 및 보안 확인을 위해 10초간 대기합니다...")
            await asyncio.sleep(10) 

            # 현재 상태 확인용 제목 출력
            title = await page.title()
            print(f"📄 현재 페이지 제목: {title}")

            # 3. 옵션 버튼 찾기
            opt_btn_sel = 'button:has-text("선택"), button[class*="OptionSelector_btn-option"]'
            
            # 버튼이 보일 때까지 최대 15초 더 대기
            try:
                await page.wait_for_selector(opt_btn_sel, timeout=15000)
            except:
                print("❌ 옵션 버튼을 찾지 못했습니다. (대기실을 못 넘었을 가능성)")
                return ["페이지 접속 실패 (옵션 버튼 없음)"]

            # 4. 옵션 클릭 및 개수 파악
            await page.click(opt_btn_sel)
            await page.wait_for_selector('li[class*="OptionSelector_option-item"]', state="visible", timeout=10000)
            
            options = await page.locator('li[class*="OptionSelector_option-item"]').all()
            print(f"📦 총 {len(options)}개의 옵션 발견")

            # 5. 옵션 순회
            for i in range(len(options)):
                # 목록이 닫혔다면 다시 열기
                if not await page.locator('li[class*="OptionSelector_option-item"]').first.is_visible():
                    await page.click(opt_btn_sel)
                    await asyncio.sleep(1)

                items = await page.locator('li[class*="OptionSelector_option-item"]').all()
                target = items[i]
                
                opt_name = (await target.locator('span[class*="option-item-tit"]').inner_text()).strip()
                print(f"🔄 [{i+1}/{len(options)}] {opt_name} 분석 중...")

                class_attr = await target.get_attribute("class") or ""
                if "is-soldout" in class_attr:
                    results.append(f"{opt_name} : 품절")
                    continue

                # 클릭 및 재고 확인
                await target.click(force=True)
                await asyncio.sleep(2)

                input_sel = 'input[data-qa-name="input-product-number"], input[class*="QuantityCounter_count"]'
                input_field = page.locator(input_sel).first
                
                if await input_field.is_visible():
                    await input_field.fill("999")
                    await page.keyboard.press("Enter")
                    
                    stock = "확인 불가"
                    try:
                        toast_sel = 'div[class*="Toast_toast-inner"]'
                        await page.wait_for_selector(toast_sel, timeout=4000)
                        toast_text = await page.inner_text(toast_sel)
                        if "재고" in toast_text:
                            match = re.search(r'\d+', toast_text)
                            stock = f"재고 {match.group()}개"
                    except:
                        stock = "재고 999+ 예상"
                    
                    results.append(f"{opt_name} : {stock}")
                    print(f"✅ {opt_name} : {stock}")
                    
                    # 수량 초기화
                    del_btn = page.locator('button[class*="OptionSelector_btn-delete"]').first
                    if await del_btn.is_visible():
                        await del_btn.click()
                        await asyncio.sleep(1)
                else:
                    results.append(f"{opt_name} : 수량 확인 불가")

            return results

        except Exception as e:
            print(f"🚨 에러 발생: {e}")
            return results if results else [f"에러: {str(e)}"]
        finally:
            await browser.close()

def send_slack(msg_list):
    if not msg_list or not SLACK_WEBHOOK_URL: return
    report = "\n".join([f"• {m}" for m in msg_list])
    payload = {"text": f"📊 *올리브영 실시간 재고 리포트*\n{report}"}
    requests.post(SLACK_WEBHOOK_URL, json=payload)

if __name__ == "__main__":
    final_results = asyncio.run(get_inventory())
    send_slack(final_results)
