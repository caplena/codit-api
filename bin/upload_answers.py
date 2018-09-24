import os
import numpy as np
import pandas as pd
import argparse
import getpass
import json

from src.codit_api_demo import CoditAPI

parser = argparse.ArgumentParser(
    description='Script to add Answers with their respective codes to question from Excel '
    'or JSON. Requires setting credentials to codit.co via the environment '
    'variables CODIT_EMAIL and CODIT_PW or entering them when required.\n'
)

parser.add_argument('question_id', type=int, help='ID of question to append answers to')
parser.add_argument('input', type=str, help='File to parse')
parser.add_argument(
    '--dry-run', action='store_true', help='If set, do not upload data but show what would be uploaded'
)

parser.add_argument('--not-reviewed', dest='reviewed', action='store_false')

parser.add_argument('--batch_size', type=int, help='Number of answers to upload in one batch', default=2000)

subparsers = parser.add_subparsers(dest='inputtype')

jsongroup = subparsers.add_parser('json')

excelgroup = subparsers.add_parser('xlsx')
excelgroup.add_argument(
    '--sheet-number', default=0, type=int, help='Sheet number to parse in Excel file (starting from 0)'
)
excelgroup.add_argument(
    '--text-col', required=True, type=str, help='Column name of the answers text in the Excel file'
)
excelgroup.add_argument(
    '--codes-substring',
    required=True,
    type=str,
    help='Substring of code-columns (sparse format). Example: Excel contains columns "Code_1", "Code_2" '
    ', ...Parse these codes by setting --codes-substring="Code"'
)
excelgroup.add_argument(
    '--code-to-ignore', type=int, help='Code ID of code to ignore (will not be uploaded)', default=None
)
excelgroup.add_argument(
    '--sourcelanguage-col',
    type=str,
    help='Source language column (optional), language-tags need to be ISO tags'
)
excelgroup.add_argument(
    '--codes-binary',
    action='store_true',
    help='If set, codes are expected to be in binary format. '
    'The code ids are assumed to be continuous and start from zero'
)

args = parser.parse_args()

# parse credentials from environment variables
email = os.environ.get('CODIT_EMAIL', None)
pw = os.environ.get('CODIT_PW', None)

question_id = args.question_id

if __name__ == '__main__':
    if args.inputtype == 'xlsx':
        # read data
        df_in = pd.read_excel(args.input, sheet_name=args.sheet_number)
        print('Adding {} answers'.format(len(df_in)))

        # renaming columns, parsing codes and separating the auxiliary-columns
        answer_cols = []

        if args.text_col not in df_in.columns:
            raise AttributeError('Text column doesn\'t exist: {}'.format(args.text_col))

        df_in = df_in.rename(columns={args.text_col: 'text'})
        df_in['text'].fillna(value='', inplace=True)
        answer_cols.append('text')

        if args.sourcelanguage_col:
            df_in = df_in.rename(columns={args.sourcelanguage_col: 'source_language'})
            answer_cols.append('source_language')

        if args.codes_substring:
            codes_cols = [col for col in df_in.columns if args.codes_substring in col]

            print("Discovered {} code columns".format(len(codes_cols)))

            if args.codes_binary:
                # The codes are in binary format, i.e. [0 0 1 0]
                from sklearn.preprocessing import MultiLabelBinarizer
                import numpy as np

                # Instantiate the binarizer
                binarizer = MultiLabelBinarizer()
                # Convert NAs to 0, concatenate columns to one list per row
                df_in['codes'] = df_in[codes_cols].fillna(0).values.tolist()
                # Prepare the binarizer: Our code IDs are 0:len(code_cols)-1
                binarizer.fit(np.asarray([range(len(codes_cols))]))

                def codes_from_binary(row):
                    binary_mat = np.asarray([[int(el) for el in row]])
                    return [int(res) for res in binarizer.inverse_transform(binary_mat)[0]]

                df_in['codes'] = df_in['codes'].apply(codes_from_binary)
            else:
                # The codes are in "list" format, i.e. for every row [code_id1, code_id2] (different lengths for rows possible)
                df_in['codes'] = df_in[codes_cols].values.tolist()
                if args.code_to_ignore:
                    df_in['codes'] = df_in['codes'].apply(lambda x:
                                                          [int(it) for it in x \
                                                           if (not pd.isnull(it)) and (not int(it) == args.code_to_ignore)])
                else:
                    df_in['codes'] = df_in['codes'
                                           ].apply(lambda x: [int(it) for it in x if not pd.isnull(it)])
            df_in['reviewed'] = args.reviewed
            answer_cols.append('codes')
            answer_cols.append('reviewed')
            df_in = df_in.drop(codes_cols, axis=1)

        # all the other columns are auxiliary columns
        auxiliary_col_names = [col_name for col_name in df_in.columns if col_name not in answer_cols]
        # also fill NaN's in auxiliary columns
        auxiliary_cols = df_in[auxiliary_col_names].fillna(value='')

        print("Appending {} auxiliary columns: {}".format(len(auxiliary_col_names), auxiliary_col_names))

        # Convert all non-numeric columns to strings (e.g. timestamps, datetime)
        for col_name in auxiliary_col_names:
            if not np.issubdtype(auxiliary_cols[col_name].dtype, np.number):
                auxiliary_cols[col_name] = auxiliary_cols[col_name].astype(str, copy=False)

        # preparing request data
        df_answers = df_in.drop(auxiliary_cols, axis=1)
        df_answers['auxiliary_columns'] = auxiliary_cols.values.tolist()
        rows = []
        for i, answer in df_answers.iterrows():
            aux_column = answer.pop('auxiliary_columns')
            answer['question'] = question_id
            rows.append({'auxiliary_columns': aux_column, 'answers': [answer.to_dict()]})

    elif args.inputtype == 'json':
        with open(args.input, 'r') as f:
            data = json.loads(f.read())
        rows = []
        parsing_json = False
        for answer in data:
            if isinstance(answer['codes'], str):
                parsing_json = True
                answer['codes'] = json.loads(answer['codes'])
                answer['reviewed'] = True
                aux_column = answer.pop('auxiliary_columns')
                answer['question'] = question_id
                rows.append({'auxiliary_columns': aux_column, 'answers': [answer.to_dict()]})
        if parsing_json:
            print('transformed codes from str to array')
    else:
        raise ValueError('Must supply either json or xls')

    # Clean the sourcelanguage col: If it's not a valid string, remove it
    if args.sourcelanguage_col:
        for row in rows:
            for ans in row['answers']:
                if not isinstance(ans['source_language'], str):
                    ans.pop('source_language')

    # add the answers using the api
    if args.dry_run:
        print('Adding the following rows: ', rows)
    else:
        # login
        api = CoditAPI('en')

        if email is None:
            email = input('Enter your email: ')
        if pw is None:
            pw = getpass.getpass(prompt='Enter your password (not displayed): ')

        login = api.login(email, pw)

        # get question info:
        question = api.getQuestion(question_id)
        project_id = question['project']
        print('Adding {} answers to question {} in project {}'.format(len(rows), question_id, project_id))
        # batch answers in order not to hit the limit
        if len(rows) < args.batch_size:
            new_answers = api.addRowsToProject(project_id, rows)
            if new_answers is not False:
                print("Added {} new answers to question {}".format(len(new_answers), question_id))
            else:
                print('error', new_answers)
        else:
            batch_number = 0
            j = 0
            while j < len(rows):
                print('Adding batch {}'.format(batch_number))
                min_idx = j
                max_idx = j + args.batch_size
                new_answers = api.addRowsToProject(project_id, rows[min_idx:max_idx])
                j = max_idx
                if new_answers is not False:
                    print(
                        "Added batch {} with {} new rows to question {}".
                        format(batch_number, len(new_answers), question_id)
                    )
                else:
                    print('error on batch {}: {}'.format(batch_number, new_answers))
                batch_number += 1
