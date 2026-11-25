async def extract_screenshots_bulk(request: PickerBulkExtractionRequestV1, *, config: PickerConfig | None = None,
                                   dependencies: PickerDependencies | None = None) -> list[PickerExtractionResultV1]:
    config = config or PickerConfig(); dependencies = dependencies or PickerDependencies()
    semaphore = asyncio.Semaphore(config.concurrency_limit)
    async def run(item):
        async with semaphore:
            return await extract_screenshot(request=item, config=config, dependencies=dependencies)
    return await asyncio.gather(*(run(item) for item in request.requests))
