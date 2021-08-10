"""
Moonstream crawlers CLI.
"""
import argparse
from datetime import datetime, timedelta, timezone
from enum import Enum
import json
import os
import sys
import time
from typing import Iterator, List

import dateutil.parser

from .ethereum import (
    crawl_blocks_executor,
    crawl_blocks,
    check_missing_blocks,
    get_latest_blocks,
    process_contract_deployments,
    DateRange,
    trending,
)
from .publish import publish_json
from .settings import MOONSTREAM_CRAWL_WORKERS
from .version import MOONCRAWL_VERSION


class ProcessingOrder(Enum):
    DESCENDING = 0
    ASCENDING = 1


def yield_blocks_numbers_lists(
    blocks_range_str: str,
    order: ProcessingOrder = ProcessingOrder.DESCENDING,
    block_step: int = 1000,
) -> Iterator[List[int]]:
    """
    Generate list of blocks.
    Block steps used to prevent long executor tasks and data loss possibility.
    """
    try:
        blocks_start_end = blocks_range_str.split("-")
        input_start_block = int(blocks_start_end[0])
        input_end_block = int(blocks_start_end[1])
    except Exception:
        print(
            "Wrong format provided, expected {bottom_block}-{top_block}, as ex. 105-340"
        )
        return

    starting_block = max(input_start_block, input_end_block)
    ending_block = min(input_start_block, input_end_block)

    stepsize = -1
    if order == ProcessingOrder.ASCENDING:
        starting_block = min(input_start_block, input_end_block)
        ending_block = max(input_start_block, input_end_block)
        stepsize = 1

    current_block = starting_block

    def keep_going() -> bool:
        if order == ProcessingOrder.ASCENDING:
            return current_block <= ending_block
        return current_block >= ending_block

    while keep_going():
        temp_ending_block = current_block + stepsize * block_step
        if order == ProcessingOrder.ASCENDING:
            if temp_ending_block > ending_block:
                temp_ending_block = ending_block + 1
        else:
            if temp_ending_block < ending_block:
                temp_ending_block = ending_block - 1
        blocks_numbers_list = list(range(current_block, temp_ending_block, stepsize))

        yield blocks_numbers_list

        if order == ProcessingOrder.ASCENDING:
            current_block += block_step
        else:
            current_block -= block_step


def ethcrawler_blocks_sync_handler(args: argparse.Namespace) -> None:
    """
    Synchronize latest Ethereum blocks with database.
    """
    starting_block: int = args.start
    while True:
        bottom_block_number, top_block_number = get_latest_blocks(args.confirmations)
        bottom_block_number = max(bottom_block_number + 1, starting_block)
        if bottom_block_number >= top_block_number:
            print(
                f"Synchronization is unnecessary for blocks {bottom_block_number}-{top_block_number - 1}"
            )
            time.sleep(5)
            continue

        for blocks_numbers_list in yield_blocks_numbers_lists(
            f"{bottom_block_number}-{top_block_number}",
            order=args.order,
        ):
            print(f"Adding blocks {blocks_numbers_list[-1]}-{blocks_numbers_list[0]}")
            # TODO(kompotkot): Set num_processes argument based on number of blocks to synchronize.
            crawl_blocks_executor(
                block_numbers_list=blocks_numbers_list,
                with_transactions=not args.notransactions,
                num_processes=args.jobs,
            )
        print(f"Synchronized blocks from {bottom_block_number} to {top_block_number}")


def ethcrawler_blocks_add_handler(args: argparse.Namespace) -> None:
    """
    Add blocks to moonstream database.
    """
    startTime = time.time()

    for blocks_numbers_list in yield_blocks_numbers_lists(args.blocks):
        print(f"Adding blocks {blocks_numbers_list[-1]}-{blocks_numbers_list[0]}")
        crawl_blocks_executor(
            block_numbers_list=blocks_numbers_list,
            with_transactions=not args.notransactions,
        )

    print(f"Required {time.time() - startTime} with {MOONSTREAM_CRAWL_WORKERS} workers")


def ethcrawler_blocks_missing_handler(args: argparse.Namespace) -> None:
    startTime = time.time()
    missing_blocks_numbers_total = []
    for blocks_numbers_list in yield_blocks_numbers_lists(args.blocks):
        print(
            f"Check missing blocks from {blocks_numbers_list[0]} to {blocks_numbers_list[-1]}"
        )
        missing_blocks_numbers = check_missing_blocks(
            blocks_numbers=blocks_numbers_list,
        )
        if len(missing_blocks_numbers) > 0:
            print(f"Found {len(missing_blocks_numbers)} missing blocks")
        missing_blocks_numbers_total.extend(missing_blocks_numbers)
    print(f"Found {len(missing_blocks_numbers_total)} missing blocks total")

    time.sleep(5)

    if (len(missing_blocks_numbers_total)) > 0:
        if args.lazy:
            print("Executed lazy block crawler")
            crawl_blocks(
                missing_blocks_numbers_total,
                with_transactions=not args.notransactions,
                verbose=args.verbose,
            )
        else:
            crawl_blocks_executor(
                missing_blocks_numbers_total,
                with_transactions=not args.notransactions,
                verbose=args.verbose,
            )
    print(
        f"Required {time.time() - startTime} with {MOONSTREAM_CRAWL_WORKERS} workers "
        f"for {len(missing_blocks_numbers_total)} missing blocks"
    )


def ethcrawler_contracts_update_handler(args: argparse.Namespace) -> None:
    results = process_contract_deployments()
    with args.outfile:
        json.dump(results, args.outfile)


def ethcrawler_trending_handler(args: argparse.Namespace) -> None:
    date_range = DateRange(
        start_time=args.start,
        end_time=args.end,
        include_start=args.include_start,
        include_end=args.include_end,
    )
    results = trending(date_range)
    humbug_token = args.humbug
    if humbug_token is None:
        humbug_token = os.environ.get("MOONSTREAM_HUMBUG_TOKEN")
    if humbug_token:
        opening_bracket = "[" if args.include_start else "("
        closing_bracket = "]" if args.include_end else ")"
        title = f"Ethereum trending addresses: {opening_bracket}{args.start}, {args.end}{closing_bracket}"
        publish_json(
            "ethereum_trending",
            humbug_token,
            title,
            results,
            tags=[f"crawler_version:{MOONCRAWL_VERSION}"],
        )
    with args.outfile as ofp:
        json.dump(results, ofp)


def main() -> None:
    parser = argparse.ArgumentParser(description="Moonstream crawlers CLI")
    parser.set_defaults(func=lambda _: parser.print_help())
    subcommands = parser.add_subparsers(description="Crawlers commands")

    time_now = datetime.now(timezone.utc)

    # Ethereum blocks parser
    parser_ethcrawler_blocks = subcommands.add_parser(
        "blocks", description="Ethereum blocks commands"
    )
    parser_ethcrawler_blocks.set_defaults(
        func=lambda _: parser_ethcrawler_blocks.print_help()
    )
    subcommands_ethcrawler_blocks = parser_ethcrawler_blocks.add_subparsers(
        description="Ethereum blocks commands"
    )

    valid_processing_orders = {
        "asc": ProcessingOrder.ASCENDING,
        "desc": ProcessingOrder.DESCENDING,
    }

    def processing_order(raw_order: str) -> ProcessingOrder:
        if raw_order in valid_processing_orders:
            return valid_processing_orders[raw_order]
        raise ValueError(
            f"Invalid processing order ({raw_order}). Valid choices: {valid_processing_orders.keys()}"
        )

    parser_ethcrawler_blocks_sync = subcommands_ethcrawler_blocks.add_parser(
        "synchronize", description="Synchronize to latest ethereum block commands"
    )
    parser_ethcrawler_blocks_sync.add_argument(
        "-n",
        "--notransactions",
        action="store_true",
        help="Skip crawling block transactions",
    )
    parser_ethcrawler_blocks_sync.add_argument(
        "-s",
        "--start",
        type=int,
        default=0,
        help="(Optional) Block to start synchronization from. Default: 0",
    )
    parser_ethcrawler_blocks_sync.add_argument(
        "-c",
        "--confirmations",
        type=int,
        default=0,
        help="Number of confirmations we require before storing a block in the database. (Default: 0)",
    )
    parser_ethcrawler_blocks_sync.add_argument(
        "--order",
        type=processing_order,
        default=ProcessingOrder.DESCENDING,
        help="Order in which to process blocks (choices: desc, asc; default: desc)",
    )
    parser_ethcrawler_blocks_sync.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=MOONSTREAM_CRAWL_WORKERS,
        help=(
            f"Number of processes to use when synchronizing (default: {MOONSTREAM_CRAWL_WORKERS})."
            " If you set to 1, the main process handles synchronization without spawning subprocesses."
        ),
    )
    parser_ethcrawler_blocks_sync.set_defaults(func=ethcrawler_blocks_sync_handler)

    parser_ethcrawler_blocks_add = subcommands_ethcrawler_blocks.add_parser(
        "add", description="Add ethereum blocks commands"
    )
    parser_ethcrawler_blocks_add.add_argument(
        "-b",
        "--blocks",
        required=True,
        help="List of blocks range in format {bottom_block}-{top_block}",
    )
    parser_ethcrawler_blocks_add.add_argument(
        "-n",
        "--notransactions",
        action="store_true",
        help="Skip crawling block transactions",
    )
    parser_ethcrawler_blocks_add.set_defaults(func=ethcrawler_blocks_add_handler)

    parser_ethcrawler_blocks_missing = subcommands_ethcrawler_blocks.add_parser(
        "missing", description="Add missing ethereum blocks commands"
    )
    parser_ethcrawler_blocks_missing.add_argument(
        "-b",
        "--blocks",
        required=True,
        help="List of blocks range in format {bottom_block}-{top_block}",
    )
    parser_ethcrawler_blocks_missing.add_argument(
        "-n",
        "--notransactions",
        action="store_true",
        help="Skip crawling block transactions",
    )
    parser_ethcrawler_blocks_missing.add_argument(
        "-l",
        "--lazy",
        action="store_true",
        help="Lazy block adding one by one",
    )
    parser_ethcrawler_blocks_missing.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print additional information",
    )
    parser_ethcrawler_blocks_missing.set_defaults(
        func=ethcrawler_blocks_missing_handler
    )

    parser_ethcrawler_contracts = subcommands.add_parser(
        "contracts", description="Ethereum smart contract related crawlers"
    )
    parser_ethcrawler_contracts.set_defaults(
        func=lambda _: parser_ethcrawler_contracts.print_help()
    )
    subcommands_ethcrawler_contracts = parser_ethcrawler_contracts.add_subparsers(
        description="Ethereum contracts commands"
    )

    parser_ethcrawler_contracts_update = subcommands_ethcrawler_contracts.add_parser(
        "update",
        description="Update smart contract registry to include newly deployed smart contracts",
    )
    parser_ethcrawler_contracts_update.add_argument(
        "-o",
        "--outfile",
        type=argparse.FileType("w"),
        default=sys.stdout,
        help="(Optional) File to write new (transaction_hash, contract_address) pairs to",
    )
    parser_ethcrawler_contracts_update.set_defaults(
        func=ethcrawler_contracts_update_handler
    )

    parser_ethcrawler_trending = subcommands.add_parser(
        "trending", description="Trending addresses on the Ethereum blockchain"
    )
    parser_ethcrawler_trending.add_argument(
        "-s",
        "--start",
        type=dateutil.parser.parse,
        default=(time_now - timedelta(hours=1, minutes=0)).isoformat(),
        help=f"Start time for window to calculate trending addresses in (default: {(time_now - timedelta(hours=1,minutes=0)).isoformat()})",
    )
    parser_ethcrawler_trending.add_argument(
        "--include-start",
        action="store_true",
        help="Set this flag if range should include start time",
    )
    parser_ethcrawler_trending.add_argument(
        "-e",
        "--end",
        type=dateutil.parser.parse,
        default=time_now.isoformat(),
        help=f"End time for window to calculate trending addresses in (default: {time_now.isoformat()})",
    )
    parser_ethcrawler_trending.add_argument(
        "--include-end",
        action="store_true",
        help="Set this flag if range should include end time",
    )
    parser_ethcrawler_trending.add_argument(
        "--humbug",
        default=None,
        help=(
            "If you would like to write this data to a Moonstream journal, please provide a Humbug "
            "token for that here. (This argument overrides any value set in the "
            "MOONSTREAM_HUMBUG_TOKEN environment variable)"
        ),
    )
    parser_ethcrawler_trending.add_argument(
        "-o",
        "--outfile",
        type=argparse.FileType("w"),
        default=sys.stdout,
        help="Optional file to write output to. By default, prints to stdout.",
    )
    parser_ethcrawler_trending.set_defaults(func=ethcrawler_trending_handler)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
