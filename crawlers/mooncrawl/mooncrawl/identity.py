import argparse
import logging
import os
import time

import requests
from sqlalchemy import text

from moonstreamdb.db import yield_db_session_ctx
from moonstreamdb.models import EthereumAddress, EthereumLabel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

COINMARKETCAP_API_KEY = os.environ.get("COINMARKETCAP_API_KEY")
if COINMARKETCAP_API_KEY is None:
    raise ValueError("COINMARKETCAP_API_KEY environment variable must be set")

CRAWL_ORIGINS = {
    "pro": "https://pro-api.coinmarketcap.com",
    "sandbox": "https://sandbox-api.coinmarketcap.com",
}


def identities_cmc_add_handler(args: argparse.Namespace) -> None:
    """
    Parse metadata for Ethereum tokens.
    """
    headers = {
        "X-CMC_PRO_API_KEY": COINMARKETCAP_API_KEY,
        "Accept": "application/json",
        "Accept-Encoding": "deflate, gzip",
    }
    if args.sandbox:
        CRAWL_ORIGIN = CRAWL_ORIGINS["sandbox"]
    else:
        CRAWL_ORIGIN = CRAWL_ORIGINS["pro"]
    url = f"{CRAWL_ORIGIN}/v1/cryptocurrency/map"

    start_n = 1
    limit_n = 5000

    while True:
        params = {
            "start": start_n,
            "limit": limit_n,
            "listing_status": args.listing_status,
        }
        try:
            r = requests.get(url=url, headers=headers, params=params)
            r.raise_for_status()
            response = r.json()
        except Exception as err:
            raise Exception(err)

        if len(response["data"]) == 0:
            logger.info("No more data, crawling finished")
            break

        with yield_db_session_ctx() as db_session:
            latest_address = 1
            latest_address_obj = (
                db_session.query(EthereumAddress.id)
                .order_by(text("id desc"))
                .limit(1)
                .one_or_none()
            )
            if latest_address_obj is not None:
                latest_address = latest_address_obj[0]

            for coin in response["data"]:
                if coin["platform"] is not None:
                    if (
                        coin["platform"]["id"] == 1027
                        and coin["platform"]["token_address"] is not None
                    ):
                        token_address = coin["platform"]["token_address"]
                        # Check if address already exists
                        address = (
                            db_session.query(EthereumAddress)
                            .filter(EthereumAddress.address == token_address)
                            .one_or_none()
                        )
                        # Add new address
                        if address is None:
                            latest_address += 1
                            eth_token_id = latest_address
                            eth_token = EthereumAddress(
                                id=eth_token_id,
                                address=token_address,
                            )
                            db_session.add(eth_token)
                            logger.info(f"Added {coin['name']} token")
                        else:
                            eth_token_id = address.id

                        label = (
                            db_session.query(EthereumLabel)
                            .filter(EthereumLabel.address_id == eth_token_id)
                            .one_or_none()
                        )
                        if label is None:
                            eth_token_label = EthereumLabel(
                                label="coinmarketcap_token",
                                address_id=eth_token_id,
                                label_data={
                                    "name": coin["name"],
                                    "symbol": coin["symbol"],
                                    "coinmarketcap_url": f'https://coinmarketcap.com/currencies/{coin["slug"]}',
                                },
                            )
                            db_session.add(eth_token_label)
                            logger.info(f"Added label for {coin['name']} token")

            db_session.commit()
        start_n += limit_n

        logger.info(
            f"Loop ended, starting new from {start_n} to {start_n + limit_n - 1}"
        )
        time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description="Crawls address identities CLI")
    parser.set_defaults(func=lambda _: parser.print_help())
    subcommands = parser.add_subparsers(description="Crawlers commands")

    parser_cmc = subcommands.add_parser("cmc", description="Coinmarketcap commands")
    parser_cmc.set_defaults(func=lambda _: parser_cmc.print_help())
    parser_cmc.add_argument(
        "-s",
        "--sandbox",
        action="store_true",
        help="Target to sandbox API",
    )

    subcommands_parser_cmc = parser_cmc.add_subparsers(
        description="Ethereum blocks commands"
    )
    parser_cmc_add = subcommands_parser_cmc.add_parser(
        "add", description="Add additional information about Ethereum addresses"
    )
    parser_cmc_add.add_argument(
        "-s",
        "--listing_status",
        default="active,inactive,untracked",
        help="Listing status of coin, by default all of them: active,inactive,untracked",
    )
    parser_cmc_add.set_defaults(func=identities_cmc_add_handler)

    # parser_label_cloud = subcommands.add_parser(
    #     "label_cloud", description="Etherscan label cloud commands"
    # )
    # parser_label_cloud.set_defaults(func=identities_get_handler)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
