import json

import pandas as pd

from typing import List

from mindsdb.integrations.libs.api_handler import APITable

from mindsdb_sql.parser import ast

from mindsdb.integrations.handlers.utilities.query_utilities import SELECTQueryParser, SELECTQueryExecutor

from mindsdb.integrations.handlers.utilities.query_utilities import INSERTQueryParser

from mindsdb.utilities.log import get_log

logger = get_log("integrations.mediawiki_handler")


class PagesTable(APITable):
    """The MediaWiki Pages Table implementation"""

    def select(self, query: ast.Select) -> pd.DataFrame:
        """Pulls MediaWiki pages data.

        Parameters
        ----------
        query : ast.Select
           Given SQL SELECT query

        Returns
        -------
        pd.DataFrame
            Sendinblue Email Campaigns matching the query

        Raises
        ------
        ValueError
            If the query contains an unsupported condition
        """

        select_statement_parser = SELECTQueryParser(
            query,
            'pages',
            self.get_columns()
        )
        selected_columns, where_conditions, order_by_conditions, result_limit = select_statement_parser.parse_query()

        title, page_id = self.validate_where_conditions(where_conditions);
        pages_df = pd.json_normalize(self.get_pages(title=title, page_id=page_id, limit=result_limit))

        select_statement_executor = SELECTQueryExecutor(
            pages_df,
            selected_columns,
            [],
            order_by_conditions
        )
        pages_df = select_statement_executor.execute_query()

        return pages_df

    def validate_where_conditions(self, conditions):
        title, page_id = None, None
        for condition in conditions:
            if condition[1] == 'title':
                if condition[0] != '=':
                    raise ValueError(f"Unsupported operator '{condition[0]}' for column '{condition[1]}' in WHERE clause.")
                title = condition[2]
            elif condition[1] == 'pageid':
                if condition[0] != '=':
                    raise ValueError(f"Unsupported operator '{condition[0]}' for column '{condition[1]}' in WHERE clause.")
                page_id = condition[2]
            else:
                raise ValueError(f"Unsupported column '{condition[1]}' in WHERE clause.")

        return title, page_id

    def insert(self, query: ast.Insert) -> None:
        """
        Updates MediaWiki pages data based on the provided SQL INSERT query.

        This method parses the given query, validates the WHERE conditions, fetches the relevant pages,
        and applies the updates.

        Parameters
        ----------
        query : ast.Insert
            Given SQL INSERT query

        Returns
        -------
        pd.DataFrame

        Raises
        ------
        ValueError
            If the query contains unsupported conditions or attempts to update unsupported columns.
        """
        insert_statements_parser = INSERTQueryParser(
            query,
            self.get_columns()
        )
        values_to_insert = insert_statements_parser.parse_query()

        if values_to_insert:
            row = values_to_insert[0]
            self.handler.call_application_api('edit', {
                'title': row['title'],
                'text': row['content'],
                'summary': row['summary'],
                'headers': json.dumps([{'Accept': 'application/json'},{'Content-Type': 'application/x-www-form-urlencoded'}])
            })

    def get_columns(self) -> List[str]:
        return ['pageid', 'title', 'original_title', 'content', 'summary', 'url', 'categories']

    def get_pages(self, title: str = None, page_id: int = None, limit: int = 20):
        query_parts = []

        query_parts.append(f'intitle:{title}') if title is not None else None
        query_parts.append(f'pageid:{page_id}') if page_id is not None else None

        search_query = ' | '.join(query_parts)

        connection = self.handler.connect()

        if search_query:
            return [self.convert_page_to_dict(connection.page(result, auto_suggest=False)) for result in connection.search(search_query, results=limit)]
        else:
            return [self.convert_page_to_dict(connection.page(result, auto_suggest=False)) for result in connection.random(pages=limit)]

    def convert_page_to_dict(self, page):
        result = {}
        attributes = self.get_columns()

        for attribute in attributes:
            try:
                result[attribute] = getattr(page, attribute)
            except KeyError:
                logger.debug(f"Error accessing '{attribute}' attribute. Skipping...")

        return result