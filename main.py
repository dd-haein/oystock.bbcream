import asyncio
import re
import os
import random
import requests
from playwright.async_api import async_playwright

TARGET_URL = os.environ.get("TARGET_URL")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

async def get_inventory():
    async with async_playwright() as p:
        # 실제 브라우저와 구분하기 어렵도록 설정
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        results = []
        try:
            print(f"🚀 접속 중: {TARGET_URL}")
            await page.goto(TARGET_URL, wait_until="networkidle")
            # 랜덤 대기 (사람이 페이지를 읽는 시간)
            await page.wait_for_timeout(random.randint(2000, 4000))

            opt_btn_sel = 'button:has-text("선택"), button[class*="OptionSelector_btn-option"]'
            
            # 1. 드롭다운 한 번만 열기
            await page.locator(opt_btn_sel).scroll_into_view_if_needed()
            await page.click(opt_btn_sel)
            await page.wait_for_selector('li[class*="OptionSelector_option-item"]', state="visible")
            
            options = await page.locator('li[class*="OptionSelector_option-item"]').all()
            total_count = len(options)
            print(f"📦 총 {total_count}개의 옵션 발견")

            for i in range(total_count):
                # 매 루프마다 목록이 닫혔는지 확인하고 필요할 때만 다시 열기
                is_visible = await page.locator('li[class*="OptionSelector_option-item"]').first.is_visible()
                if not is_visible:
                    print("🔄 목록이 닫혀있어 다시 엽니다.")
                    await page.click(opt_btn_sel)
                    await page.wait_for_timeout(random.randint(800, 1200))

                # 현재 작업할 요소 확보
                items = await page.locator('li[class*="OptionSelector_option-item"]').all()
                target = items[i]
                
                # 옵션명 추출
                name_el = target.locator('span[class*="option-item-tit"]')
                opt_name = (await name_el.inner_text()).strip()

                # 품절 체크
                class_attr = await target.get_attribute("class") or ""
                if "is-soldout" in class_attr:
                    results.append(f"{opt_name} : 품절")
                    print(f"🚫 {opt_name} : 품절")
                    continue

                # 2. 정밀 클릭 (마우스 이동 포함)
                box = await target.bounding_box()
                if box:
                    # 마우스를 해당 위치로 이동시킨 후 클릭 (인간적인 동작)
                    await page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                    await page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                else:
                    await target.click(force=True)
                
                await page.wait_for_timeout(random.randint(1200, 1800))

                # 3. 수량 입력창 확인
                input_sel = 'input[data-qa-name="input-product-number"], input[class*="QuantityCounter_count"]'
                input_field = page.locator(input_sel).first
                
                if await input_field.is_visible():
                    await input_field.fill("999")
                    await page.keyboard.press("Enter")
                    
                    stock = "999+ 예상"
                    try:
                        toast_sel = 'div[class*="Toast_toast-inner"]'
                        # 토스트 대기 시간을 약간 유동적으로
                        await page.wait_for_selector(toast_sel, timeout=3500)
                        toast_text = await page.inner_text(toast_sel)
                        if "재고" in toast_text:
                            match = re.search(r'\d+', toast_text)
                            stock = f"재고 {match.group()}개"
                            print(f"✅ {opt_name} : {stock}")
                    except:
                        pass
                    
                    results.append(f"{opt_name} : {stock}")
                    
                    # 삭제 버튼 클릭
                    del_btn = page.locator('button[class*="OptionSelector_btn-delete"]').first
                    if await del_btn.is_visible():
                        await del_btn.click()
                        await page.wait_for_timeout(random.randint(600, 1000))
                else:
                    results.append(f"{opt_name} : 입력창 미발견")

            return results

        except Exception as e:
            print(f"🚨 중단됨: {e}")
            return results if results else [f"에러 발생: {str(e)}"]
        finally:
            await browser.close()

# (send_slack 함수는 동일)
