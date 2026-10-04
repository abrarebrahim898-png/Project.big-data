"""Optional PySpark route for files larger than the Python batch threshold."""


def make_spark(app_name="orders-data-pipeline"):
    from pyspark.sql import SparkSession
    return SparkSession.builder.appName(app_name).config("spark.mongodb.write.connection.uri", "mongodb://localhost:27017").getOrCreate()


def read_with_spark(spark, file_path):
    return spark.read.option("header", True).option("inferSchema", False).csv(file_path)


def spark_quality_analysis(dataframe):
    return {"rows": dataframe.count(), "columns": dataframe.columns, "partitions": dataframe.rdd.getNumPartitions()}


def write_mongo_connector(dataframe, database, collection, mode="append"):
    return dataframe.write.format("mongodb").option("spark.mongodb.write.database", database).option("spark.mongodb.write.collection", collection).mode(mode).save()
