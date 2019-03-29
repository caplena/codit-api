import os, time

import pytest

from src.codit_api_demo import CoditAPI

api = CoditAPI('en')

baseuri = os.environ.get('BASEURI')
codit_email = os.environ.get('CODIT_EMAIL')
codit_pw = os.environ.get('CODIT_PW')

if baseuri:
    api.baseURI = baseuri
api.login(codit_email, codit_pw)


def test_list_projects():
    _ = api.listProjects()


def test_list_inheritable_projects():
    _ = api.listInheritableProjects()


@pytest.mark.parametrize('run,async', [(1, False), (2, True)])
def test_workflow(run, async):
    codebook = [
        {
            'id': 1,
            'label': 'Code 1',
            'category': 'CATEGORY 1'
        }, {
            'id': 20,
            'label': 'Code 2',
            'category': 'CATEGORY 2'
        }
    ]
    questions = [{'name': 'Question 1', 'codebook': codebook}]
    # make sure to have at least 15 answers reviewed to enble predictions
    rows_init = [
        {
            "answers":
            [{
                "text": "Answer-text 1",
                "question": "Question 1",
                "codes": [1, 20],
                "reviewed": True
            }],
            "auxiliary_columns": ["ID 1", "Some other column value 1"]
            # The values of the additional columns: Needs to be in same order as auxiliary_column_names of survey
        },
        {
            "answers": [{
                "text": "Answer-text 2",
                "question": "Question 1",
                "codes": [1],
                "reviewed": True
            }],
            "auxiliary_columns": ["ID 1", "Some other column value 1"]
        },
        {
            "answers": [{
                "text": "Answer-text 3",
                "question": "Question 1",
                "codes": [20],
                "reviewed": True
            }],
            "auxiliary_columns": ["ID 1", "Some other column value 1"]
        },
        {
            "answers": [{
                "text": "Answer-text 4",
                "question": "Question 1",
                "codes": [20],
                "reviewed": True
            }],
            "auxiliary_columns": ["ID 1", "Some other column value 1"]
        },
        {
            "answers":
            [{
                "text": "Answer-text 5",
                "question": "Question 1",
                "codes": [1, 20],
                "reviewed": True
            }],
            "auxiliary_columns": ["ID 1", "Some other column value 1"]
        },
        {
            "answers": [{
                "text": "Answer-text 6",
                "question": "Question 1",
                "codes": [1],
                "reviewed": True
            }],
            "auxiliary_columns": ["ID 1", "Some other column value 1"]
        },
        {
            "answers":
            [{
                "text": "Answer-text 7",
                "question": "Question 1",
                "codes": [1, 20],
                "reviewed": True
            }],
            "auxiliary_columns": ["ID 1", "Some other column value 1"]
        },
        {
            "answers": [{
                "text": "Answer-text 8",
                "question": "Question 1",
                "codes": [1],
                "reviewed": True
            }],
            "auxiliary_columns": ["ID 1", "Some other column value 1"]
        },
        {
            "answers": [{
                "text": "Answer-text 9",
                "question": "Question 1",
                "codes": [1],
                "reviewed": False
            }],
            "auxiliary_columns": ["ID 1", "Some other column value 1"]
        }
    ] * 3
    num_projects_before = len(api.listProjects())
    new_project = api.createProject(
        "My new project",
        "de",
        auxiliary_column_names=['ID', 'some other column'],
        translate=True,
        questions=questions,
        rows=rows_init,
        async=async,
        request_training=False
    )
    try:
        if async:
            time.sleep(20)
        num_projects_after = len(api.listProjects())
        assert num_projects_after == num_projects_before + 1
        assert len(new_project['questions']) == 1
        question_id = new_project['questions'][0]['id']
        # only request training for one workflow as it's exactly the same and creates load
        if run == 1:

            _ = api.requestPredictions(question_id, request_svm_now=True)

            # wait for the predictions to arrive
            MAX_PRED_TIME = 35
            delay = 0
            predictions = None
            while predictions is None and delay <= MAX_PRED_TIME:
                predictions = api.getPredictions(question_id)
                timestep = 5
                time.sleep(timestep)
                delay = delay + timestep

            n_not_reviewed = len([row for row in rows_init if not row['answers'][0]['reviewed']])
            assert predictions is not None
            assert len(predictions['answers']) == n_not_reviewed

        additional_rows = [
            {
                "answers": [{
                    "text": "Answer-text 1 new data",
                    "question": question_id,
                    "reviewed": False
                }],
                "auxiliary_columns": ["ID 1", "Some other column value 1"]
                # The values of the additional columns: Needs to be in same order as auxiliary_column_names of survey
            },
            {
                "answers": [{
                    "text": "Answer-text 2 new data",
                    "question": question_id,
                    "reviewed": False
                }],
                "auxiliary_columns": ["ID 1", "Some other column value 1"]
            }
        ]
        new_answers = api.addRowsToProject(
            new_project['id'], additional_rows, async=async, request_training=False
        )
        if async:
            time.sleep(20)
        answers = api.listAnswers(question_id, no_group=True)
        assert len(rows_init) + len(additional_rows) == len(answers)

    finally:
        _ = api.deleteProject(new_project['id'])
        assert num_projects_before == len(api.listProjects())
