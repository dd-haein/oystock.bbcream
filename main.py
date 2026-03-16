import asyncio
import re
import os
import requests
from playwright.async_api import async_playwright

# --- 설정 ---
TARGET_URL = "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000233123"
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

async def get_inventory():
    async with async_playwright() as p:
        # 브라우저 실행
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = await context.new_page()
        
        results = []
        try:
            await page.goto(TARGET_URL, wait_until="networkidle")
            
            # 1. 옵션 드롭다운 클릭
            opt_btn = page.locator('button[class*="OptionSelector_btn-option"]')
            await opt_btn.click()
            await page.wait_for_timeout(1500)

            # 2. 모든 옵션 요소 가져오기
            options = await page.locator('li[class*="OptionSelector_option-item"]').all()
            total_count = len(options)
            
            for i in range(total_count):
                # 루프마다 요소 다시 로드 (DOM 변화 대응)
                items = await page.locator('li[class*="OptionSelector_option-item"]').all()
                target = items[i]
                
                # 옵션명 추출
                name_el = target.locator('span[class*="option-item-tit"]')
                opt_name = (await name_el.inner_text()).strip()

                # 품절 체크
                class_attr = await target.get_attribute("class")
                if "is-soldout" in class_attr:
                    results.append(f"{opt_name} : 품절")
                    continue

                # 3. 좌표 기반 정밀 클릭 (콘솔 11차 로직)
                box = await target.bounding_box()
                if box:
                    await page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                
                await page.wait_for_timeout(1200)

                # 4. 수량 입력창 찾기
                input_sel = 'input[data-qa-name="input-product-number"], input[class*="QuantityCounter_count"]'
                input_field = page.locator(input_sel).first
                
                if await input_field.is_visible():
                    # 999 입력 (Playwright의 fill은 내부적으로 select & insertText와 유사하게 동작)
                    await input_field.fill("999")
                    await page.keyboard.press("Enter")
                    
                    # 5. 토스트 메시지 감지
                    stock = "확인 불가 (재고 999+)"
                    try:
                        # 토스트가 나타날 때까지 대기
                        toast_sel = 'div[class*="Toast_toast-inner"]'
                        await page.wait_for_selector(toast_sel, timeout=4000)
                        toast_text = await page.inner_text(toast_sel)
                        
                        if "재고" in toast_text:
                            match = re.search(r'\d+', toast_text)
                            if match:
                                stock = f"재고 {match.group()}개"
                    except:
                        pass # 토스트 안 뜨면 999+로 간주
                    
                    results.append(f"{opt_name} : {stock}")
                    
                    # 다음 옵션을 위해 현재 옵션 삭제 (X 버튼)
                    del_btn = page.locator('button[class*="OptionSelector_btn-delete"]')
                    if await del_btn.is_visible():
                        await del_btn.click()
                        await page.wait_for_timeout(800)
                else:
                    results.append(f"{opt_name} : 입력창 미발견")

            return results

        except Exception as e:
            print(f"오류 발생: {e}")
            return None
        finally:
            await browser.close()

def send_slack(msg_list):
    if not msg_list or not SLACK_WEBHOOK_URL: return
    report = "\n".join([f"• {m}" for m in msg_list])
    payload = {"text": f"📊 *실시간 재고 리포트*\n{report}"}
    requests.post(SLACK_WEBHOOK_URL, json=payload)

if __name__ == "__main__":
    final_results = asyncio.run(get_inventory())
    send_slack(final_results)
