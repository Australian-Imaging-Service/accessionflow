from .base import data_store_group

store_group = data_store_group(
    name="store",
    help="Deposits labelled accessions from a staging directory in a data store",
)

check_store_group = data_store_group(
    name="check-store",
    help=(
        "Checks what has been deposited in a data store against the staging directory "
        "it was deposited from, and logs all files that haven't been"
    ),
)
