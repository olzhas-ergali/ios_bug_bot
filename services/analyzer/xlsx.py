import pandas as pd


def get_cities():
    data = pd.read_excel('data/cities.xlsx')
    cities = data.iloc[:, 0].unique()
    return cities
