# We'll start by importing the DAG object
from datetime import timedelta

from airflow import DAG
# We need to import the operators used in our tasks
from airflow.operators.python_operator import PythonOperator
from airflow.operators.postgres_operator import PostgresOperator
from sqlalchemy import create_engine

# We then import the days_ago function
from airflow.utils.dates import days_ago

import pandas as pd
import psycopg2
import os

# get dag directory path
dag_path = os.getcwd()


def transform_data():
    booking = pd.read_csv(f"{dag_path}/raw_data/booking.csv", low_memory=False)
    client = pd.read_csv(f"{dag_path}/raw_data/client.csv", low_memory=False)
    hotel = pd.read_csv(f"{dag_path}/raw_data/hotel.csv", low_memory=False)

    # merge booking with client
    data = pd.merge(booking, client, on='client_id')
    data.rename(columns={'name': 'client_name', 'type': 'client_type'}, inplace=True)

    # merge booking, client & hotel
    data = pd.merge(data, hotel, on='hotel_id')
    data.rename(columns={'name': 'hotel_name'}, inplace=True)

    # make date format consistent
    data.booking_date = pd.to_datetime(data.booking_date, infer_datetime_format=True)

    # make all cost in GBP currency
    data.loc[data.currency == 'EUR', ['booking_cost']] = data.booking_cost * 0.8
    data.currency.replace("EUR", "GBP", inplace=True)

    # remove unnecessary columns
    data = data.drop('address', 1)

    # load processed data
    data.to_csv(f"{dag_path}/processed_data/processed_data.csv", index=False)



def load_data():
    records = pd.read_csv(f"{dag_path}/processed_data/processed_data.csv")
    engine = create_engine('postgresql://airflow:airflow@postgres:5432/airflow')
    records.to_sql('booking_record', engine, if_exists='append', index=False)


# initializing the default arguments that we'll pass to our DAG
default_args = {
    'owner': 'airflow',
    'start_date': days_ago(5)
}

ingestion_dag = DAG(
    'booking_ingestion',
    default_args=default_args,
    description='Aggregates booking records for data analysis',
    schedule_interval=timedelta(days=1),
    catchup=False
)

task_1 = PythonOperator(
    task_id='transform_data',
    python_callable=transform_data,
    dag=ingestion_dag,
)

task_2 = PostgresOperator(
        task_id="create_table",
        postgres_conn_id= "postgres_db",
        sql="""
             CREATE TABLE IF NOT EXISTS booking_record (
                    client_id INTEGER NOT NULL,
                    booking_date varchar(50) NOT NULL,
                    room_type varchar(512) NOT NULL,
                    hotel_id INTEGER NOT NULL,
                    booking_cost NUMERIC,
                    currency varchar(50),
                    age INTEGER,
                    client_name varchar(512),
                    client_type varchar(512),
                    hotel_name varchar(512)
                    );
          """,
        dag=ingestion_dag
    )

task_3 = PythonOperator(
    task_id='load_data',
    python_callable=load_data,
    dag=ingestion_dag,
)


task_1 >> task_2 >> task_3